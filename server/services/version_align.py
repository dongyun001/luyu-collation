"""对校引擎（F13）：底本 × 参照本的字符级对齐，**纯规则、不调模型**。

四法引擎里"对校"这一路：`docs/TECH_DESIGN.md §2` 选型为 `difflib`，理由是
它给出的是**确定性**结果——同一对输入永远同一条异文清单，可复现、可核对，
这正是 `docs/EVAL.md §1` 对异文"必须能给出别本依据"的天然满足。

产出语义（契约见 `docs/API.md §7`，本文件只实现，不改口径）：
  * **只产出 `异文` 一类**：两本都有、写法不同的片段。对校的产物是*版本差异*，
    不是校改建议；把版本差异硬塞进讹/衍/脱/通假会污染理校的五类语义。
  * 一方有、一方无的片段进 `presenceDiffs`（`reference-missing` / `reference-extra`），
    **不计入五类**——因为脱/衍带方向性（"谁相对谁是脱"），而对校只说得清"两本不一致"。
  * `confidence` 固定 1.0：字符级对齐没有"可信度"概念，保留该字段只为让前端与导出
    复用同一套数据结构。

`autojunk` 必须是 **False**（实测理由）：中文常用字在一段 5000 字文本里出现次数远超
"popular 元素"的 1% 阈值，开 autojunk 会把绝大多数汉字当噪声屏蔽。同一对 5000 字文本，
`autojunk=False` 得到 115 个对齐块、耗时 0.42 秒；`autojunk=True` 塌成 2 个块——
异文全被吞掉。0.42 秒的代价换来正确的对齐，值得。
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

# 与 API.md §7 的 presenceDiffs.kind 取值一致
PRESENCE_MISSING = "reference-missing"  # 底本有、参照本此处缺
PRESENCE_EXTRA = "reference-extra"  # 参照本此处多、底本无
# 对校只出这一类（API.md §7）
COMPARE_TYPE = "异文"
COMPARE_CONFIDENCE = 1.0


@dataclass(frozen=True)
class AlignedItem:
    """一条版本异文。`offset` 是 `original` 在**底本**中的首字符下标。"""

    type: str
    original: str
    suggested: str
    reason: str
    offset: int
    confidence: float
    source: str


@dataclass(frozen=True)
class PresenceDiff:
    """一处版本存缺。

    `offset` 的语义对两种 kind 是统一的——**一律是底本中的下标**：
      * `reference-missing`：该片段在底本中的起点；
      * `reference-extra`：该片段在底本中的**插入点**（左邻锚点之后），底本里没有对应内容，
        因此用插入点而不是"参照本里的下标"，前端才能拿它去底本上定位。
    """

    source: str
    kind: str
    text: str
    offset: int


@dataclass(frozen=True)
class AlignResult:
    items: list[AlignedItem]
    presence_diffs: list[PresenceDiff]


def _reason(reference_name: str, suggested: str) -> str:
    """依据就是版本本身：API.md §7 规定的模板「「甲本」作「南昌故郡」」。"""
    return f"「{reference_name}」作「{suggested}」"


def align_pair(base_text: str, reference_name: str, reference_text: str) -> AlignResult:
    """底本与单个参照本对齐。纯函数：同输入必同输出，无随机、无外部状态。"""
    items: list[AlignedItem] = []
    presence: list[PresenceDiff] = []

    matcher = difflib.SequenceMatcher(None, base_text, reference_text, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        base_segment = base_text[i1:i2]
        reference_segment = reference_text[j1:j2]

        if base_segment and reference_segment:
            # 两本都有、写法不同 → 异文
            items.append(
                AlignedItem(
                    type=COMPARE_TYPE,
                    original=base_segment,
                    suggested=reference_segment,
                    reason=_reason(reference_name, reference_segment),
                    offset=i1,
                    confidence=COMPARE_CONFIDENCE,
                    source=reference_name,
                )
            )
        elif base_segment:
            # 底本有、参照本无 → 参照本此处存缺
            presence.append(
                PresenceDiff(
                    source=reference_name,
                    kind=PRESENCE_MISSING,
                    text=base_segment,
                    offset=i1,
                )
            )
        else:
            # 参照本多出 → 以底本的插入点为定位（i1 == i2）
            presence.append(
                PresenceDiff(
                    source=reference_name,
                    kind=PRESENCE_EXTRA,
                    text=reference_segment,
                    offset=i1,
                )
            )

    return AlignResult(items=items, presence_diffs=presence)


def align_versions(
    base_text: str, references: list[tuple[str, str]]
) -> AlignResult:
    """底本 × 多个参照本，归并成一份清单。

    归并规则（API.md §7）：
      * 多个参照本命中同一处时，**每个参照本各出一条**（`source` 不同），不做跨本合并——
        "甲本作 A、乙本作 B"是两条信息，并成一条会丢掉其中一家的写法；
      * 排序按 `offset` 升序；同一位置按传入顺序（参照本在请求里的先后），保证稳定可复现。
    """
    pairs: list[tuple[int, int, AlignedItem | PresenceDiff]] = []
    for index, (name, text) in enumerate(references):
        result = align_pair(base_text, name, text)
        for item in result.items:
            pairs.append((item.offset, index, item))
        for diff in result.presence_diffs:
            pairs.append((diff.offset, index, diff))

    pairs.sort(key=lambda triple: (triple[0], triple[1]))
    return AlignResult(
        items=[entry for _, _, entry in pairs if isinstance(entry, AlignedItem)],
        presence_diffs=[entry for _, _, entry in pairs if isinstance(entry, PresenceDiff)],
    )
