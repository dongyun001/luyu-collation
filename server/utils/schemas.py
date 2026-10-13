"""pydantic 模型：请求校验 + 大模型输出校验（API.md §2 的字段约束在此落地）。

质量红线：模型返回的 JSON 必须先过这里才能进 UI；校验失败走 LLM_BAD_JSON 降级，
单条不合契约则丢弃并计入 droppedCount（API.md §2）。
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 非功能需求：单次校勘文本 ≤5000 字（PRD §5）
MAX_TEXT_LEN = 5000

CollationType = Literal["讹字", "衍文", "脱文", "通假", "异文"]
COLLATION_TYPES: tuple[str, ...] = ("讹字", "衍文", "脱文", "通假", "异文")

# F9 多维度文献分析（API.md §6）：七个维度 key 固定，顺序即雷达图轴序（docs/VISUAL.md §4.1）
DIMENSION_KEYS: tuple[str, ...] = (
    "nature",
    "dating",
    "authorship",
    "school",
    "edition",
    "language",
    "collation",
)
DIMENSION_LABELS: dict[str, str] = {
    "nature": "文献性质",
    "dating": "成书年代",
    "authorship": "作者与编纂",
    "school": "学派与思想",
    "edition": "版本与流传",
    "language": "语言文字特征",
    "collation": "校勘要点",
}

# 知识图谱节点分类（docs/VISUAL.md §4.3）
ENTITY_KINDS: tuple[str, ...] = ("人物", "著作", "学派", "地名", "职官", "年代")

# 长文本抽样参数（API.md §6）：超过阈值取「首段 + 尾段」，并在响应里如实标注 sampled
ANALYZE_SAMPLE_THRESHOLD = 2000
ANALYZE_SAMPLE_HEAD = 1200
ANALYZE_SAMPLE_TAIL = 600


def normalize_confidence(value: float) -> float:
    """把模型给的置信度归一化并做范围校验（collate 与 analyze 共用同一条规则）。

    容忍模型用百分数（95）而非小数（0.95）作答——实测两种写法都会出现；
    其余越界一律判为不合契约（调用方负责丢弃与计数）。
    """
    if not math.isfinite(value):
        raise ValueError("confidence 必须是有限数值")
    if 1.0 < value <= 100.0:
        value = value / 100.0
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"confidence 越界：{value}")
    return value


# ---------------------------------------------------------------------------
# 请求
# ---------------------------------------------------------------------------
class CollateOptions(BaseModel):
    """POST /collate 的 options，可整体省略（API.md §2）。"""

    model_config = ConfigDict(extra="ignore")

    checkTypes: list[CollationType] = Field(
        default_factory=lambda: list(COLLATION_TYPES), min_length=1
    )
    produceTranslation: bool = True
    referenceEdition: str = "通行本"


class CollateRequest(BaseModel):
    """POST /collate 请求体。长度上限由路由单独判，以便回 413 而非 400。"""

    model_config = ConfigDict(extra="ignore")

    text: str
    options: CollateOptions = Field(default_factory=CollateOptions)

    @field_validator("options", mode="before")
    @classmethod
    def _treat_null_as_omitted(cls, value: Any) -> Any:
        """显式传 null 与整体省略等价（API.md §2「options 可省略」）。

        前端用 JSON.stringify 时很容易把 undefined 之外的 null 发出来，
        这里按「取默认值」处理，避免一个空选项把整次校勘打成 400。
        """
        return {} if value is None else value


# ---------------------------------------------------------------------------
# 大模型输出（TECH_DESIGN §5 的输出契约；注意契约里没有 id）
# ---------------------------------------------------------------------------
class ModelItem(BaseModel):
    """模型输出契约中的单条校勘建议。"""

    model_config = ConfigDict(extra="ignore")

    type: CollationType
    original: str = Field(min_length=1)
    suggested: str
    # 理由即本作品相对「通用错别字工具」的差异点，缺理由的条目不进入 UI
    reason: str = Field(min_length=1)
    confidence: float
    # 模型给的 offset 会被**校验后采用**：位置合法且该处文本确实等于 original 才采信，
    # 否则退回首次出现（见 routers/collate.py 的 _locate）。这样重复出现的同一个字
    # 才能被分别标出，而不是一律标到第一处。
    offset: int | None = None

    @field_validator("confidence")
    @classmethod
    def _normalize_confidence(cls, value: float) -> float:
        """容忍模型用百分数（95）而非小数（0.95）作答，其余越界一律判为不合契约。"""
        return normalize_confidence(value)

    @model_validator(mode="after")
    def _suggested_must_differ_from_original(self) -> "ModelItem":
        """`suggested` 必须与 `original` 不同（API.md §2 字段约束）。

        相同即「空操作」，有害无益：UI 会显示成「X → X」，校勘记会写出「一作 X」的自指句，
        阶段二要喂给对校引擎的异文清单也无从结构化。实测中真实模型正是这样处理异文类的
        （把别本写法只写进 reason），所以这里做成硬约束：不合契约的条目丢弃并计入 droppedCount。
        """
        if self.suggested == self.original:
            raise ValueError("suggested 与 original 相同，属空操作，不成其为校勘建议")
        return self


class ModelOutputEnvelope(BaseModel):
    """模型原始 JSON 的信封校验。

    items 故意用 list[Any]：条目要逐条单独校验，让不合契约的单条丢弃并计数
    （API.md §2 的 droppedCount），而不是一条坏数据废掉整次校勘。
    """

    model_config = ConfigDict(extra="ignore")

    items: list[Any]
    translation: str = ""


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------
class CollationItem(BaseModel):
    """对外输出的校勘建议：id 由后端按序分配（API.md §2）。"""

    id: int
    type: CollationType
    original: str
    suggested: str
    reason: str
    confidence: float
    offset: int


class CollateResponse(BaseModel):
    requestId: str
    model: str
    elapsedMs: int
    items: list[CollationItem]
    translation: str
    droppedCount: int


class HealthResponse(BaseModel):
    status: str
    llmProvider: str
    ocrConfigured: bool
    # 复现信息（EVAL §8）：当前生效的 Prompt 版本 / 规则开关 / 采样温度。
    # 前两项由 eval/run_compare.py 自动写进结果 CSV，避免"这批数字跑的是哪个 Prompt"靠人手记。
    collatePrompt: str
    rulesEnabled: bool
    llmTemperature: float


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# F9 多维度文献分析（API.md §6）
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    """POST /analyze 请求体。

    `dimensions` 可省略（默认全 7 维）；传未知 key 会在这里被拒，
    由 main.py 的统一处理器转成 400 / INVALID_REQUEST（而不是 422）。
    """

    model_config = ConfigDict(extra="ignore")

    text: str
    dimensions: list[str] | None = None

    @field_validator("dimensions")
    @classmethod
    def _validate_dimensions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return list(DIMENSION_KEYS)
        unknown = [key for key in value if key not in DIMENSION_KEYS]
        if unknown:
            raise ValueError(f"未知的维度 key：{'、'.join(unknown)}")
        if not value:
            raise ValueError("dimensions 不能是空数组（省略即取全部 7 维）")
        return value


class ModelDimension(BaseModel):
    """模型输出契约里的单个维度判断。"""

    model_config = ConfigDict(extra="ignore")

    key: str
    judgment: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    confidence: float
    uncertain: bool = False
    knowledgePoints: list[str] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        if value not in DIMENSION_KEYS:
            raise ValueError(f"未知的维度 key：{value}")
        return value

    @field_validator("confidence")
    @classmethod
    def _normalize_confidence(cls, value: float) -> float:
        return normalize_confidence(value)

    @model_validator(mode="after")
    def _no_evidence_means_uncertain(self) -> "ModelDimension":
        """无依据不许自称确定（API.md §6 字段约束）。

        这里**不丢弃**而是降级为「存疑」：本 Prompt 的一贯主张是"不确定就降置信、
        标存疑"，而不是把话咽回去。丢弃会让雷达少一根轴，反而更失真。
        """
        if not self.evidence:
            self.uncertain = True
        return self


class ModelEntity(BaseModel):
    """模型输出契约里的实体（知识图谱节点）。"""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    kind: str
    note: str = ""

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        if value not in ENTITY_KINDS:
            raise ValueError(f"未知的实体类别：{value}")
        return value


class ModelRelation(BaseModel):
    """模型输出契约里的关系（知识图谱边）。端点是否存在由路由校验。"""

    model_config = ConfigDict(extra="ignore")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relation: str = ""


class ModelAnalyzeEnvelope(BaseModel):
    """分析输出的信封校验：各列表用 list[Any] 逐项校验，坏一条不废整次（同 collate）。"""

    model_config = ConfigDict(extra="ignore")

    dimensions: list[Any]
    entities: list[Any] = Field(default_factory=list)
    relations: list[Any] = Field(default_factory=list)


class DimensionScore(BaseModel):
    """对外输出的维度判断（missing 为占位语义，见 API.md §6）。"""

    key: str
    label: str
    judgment: str
    evidence: list[str]
    confidence: float
    uncertain: bool
    missing: bool
    knowledgePoints: list[str]


class AnalyzeEntity(BaseModel):
    name: str
    kind: str
    note: str


class AnalyzeRelation(BaseModel):
    source: str
    target: str
    relation: str


class AnalyzeResponse(BaseModel):
    requestId: str
    model: str
    elapsedMs: int
    analyzedChars: int
    sampled: bool
    dimensions: list[DimensionScore]
    entities: list[AnalyzeEntity]
    relations: list[AnalyzeRelation]
    droppedCount: int


# ---------------------------------------------------------------------------
# F13 版本对勘（API.md §7）—— 纯规则端点，不调模型
# ---------------------------------------------------------------------------
#: 参照本数量上限（API.md §7）。多于 3 个不算是"对勘"，是"批量比对"，交互与结论都会走样。
MAX_REFERENCES = 3


class CompareReference(BaseModel):
    """一个参照本。`name` 会出现在异文的 `reason` 与 `source` 里，故不能为空。"""

    model_config = ConfigDict(extra="ignore")

    name: str
    text: str


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    baseText: str
    references: list[CompareReference]


class CompareItem(BaseModel):
    """对校产出：`type` 只能是「异文」（API.md §7 的收紧契约）。"""

    id: int
    type: Literal["异文"]
    original: str
    suggested: str
    reason: str
    offset: int
    confidence: float
    source: str


class PresenceDiffItem(BaseModel):
    """版本存缺。`offset` 一律是**底本**中的下标（详见 version_align.PresenceDiff）。"""

    source: str
    kind: Literal["reference-missing", "reference-extra"]
    text: str
    offset: int


class CompareResponse(BaseModel):
    requestId: str
    elapsedMs: int
    items: list[CompareItem]
    presenceDiffs: list[PresenceDiffItem]
    #: 恒为 0（没有模型输出就没有不合契约的条目可丢）；保留只为与 /collate 形状一致
    droppedCount: int
