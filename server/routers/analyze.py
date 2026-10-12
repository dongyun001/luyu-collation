"""POST /api/v1/analyze —— 多维度文献分析（F9），契约见 API.md §6。

调用链：限流 → 入参校验 → 长文本抽样 → Prompt 组装 → 调模型 → 取 JSON →
逐项 schema 校验（不合契约的丢弃计 droppedCount）→ 补齐未判断维度 → 抽实体/关系。

设计要点（TECH_DESIGN §5）：

- **与 /collate 完全独立**：不产出校勘建议、不改动原文。分析失败不影响已到货的校勘结果。
- **缺失维度补占位而不是删掉**：`missing: true` 让雷达图 7 轴齐整，UI 明示"该维度未能判断"，
  这样图形不会因为少一根轴而失真，也不会被误读成"判断为否"（docs/VISUAL.md §4.1）。
- **关系端点必须落在实体里**，否则丢弃并计数——脏边进了图，知识图谱就变成"看着热闹"。
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import ValidationError

from ..config import get_settings
from ..services.llm import complete_json, extract_json_object
from ..services.prompt_loader import load_prompt, render
from ..utils.errors import INTERNAL_ERROR, INVALID_REQUEST, LLM_BAD_JSON, TEXT_TOO_LONG, ApiError
from ..utils.rate_limit import check_rate_limit
from ..utils.schemas import (
    ANALYZE_SAMPLE_HEAD,
    ANALYZE_SAMPLE_TAIL,
    ANALYZE_SAMPLE_THRESHOLD,
    DIMENSION_KEYS,
    DIMENSION_LABELS,
    MAX_TEXT_LEN,
    AnalyzeEntity,
    AnalyzeRelation,
    AnalyzeRequest,
    AnalyzeResponse,
    DimensionScore,
    ModelAnalyzeEnvelope,
    ModelDimension,
    ModelEntity,
    ModelRelation,
)

router = APIRouter()

ANALYZE_PROMPT = "analyze_v1"

#: 未能判断的维度在 UI 上的文案（与 docs/VISUAL.md §4.2 的口径一致）
MISSING_JUDGMENT = "本段文本信息不足，未能判断"

#: 抽样时插入的分隔标记，让模型知道自己看的是首尾拼接而非连续全文
_SAMPLE_MARKER = "\n……（中间部分省略）……\n"


def _new_request_id() -> str:
    """形如 req_20261012_ab12cd（与 /collate 同一形状，便于日志检索）。"""
    return f"req_{datetime.now().strftime('%Y%m%d')}_{secrets.token_hex(3)}"


def _client_key(request: Request) -> str:
    """取客户端标识用于限流；部署在反向代理后时认 X-Forwarded-For 的第一跳。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _describe_validation_error(exc: ValidationError) -> str:
    """把 pydantic 报错压成一行，便于排查模型输出的哪一项不合契约。"""
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "根"
        parts.append(f"{location}: {error.get('msg', '校验失败')}")
    return "；".join(parts)


def sample_text(text: str) -> tuple[str, bool]:
    """长文本抽样：超过阈值时取「首段 + 尾段」，返回 (送模文本, 是否抽样)。

    为什么抽样而不是截断：古籍的篇首（题名、起句）与篇尾（结语、题识）信息密度最高，
    只取头部会丢掉"这一篇是什么"的关键线索。中间省略处插入标记，避免模型把首尾
    误当成连续文本（例如误判成脱文）。
    """
    if len(text) <= ANALYZE_SAMPLE_THRESHOLD:
        return text, False
    head = text[:ANALYZE_SAMPLE_HEAD]
    tail = text[-ANALYZE_SAMPLE_TAIL:]
    return f"{head}{_SAMPLE_MARKER}{tail}", True


def _build_prompts(text: str, dimensions: list[str]) -> tuple[str, str]:
    """组装 (system, user) 两条 Prompt。"""
    prompt = load_prompt(ANALYZE_PROMPT)
    system_prompt = prompt.get("SYSTEM")
    user_template = prompt.get("USER")
    if not system_prompt or not user_template:
        raise ApiError(INTERNAL_ERROR, "分析 Prompt 资产缺少 SYSTEM 或 USER 段")

    listed = "\n".join(f"- {key} {DIMENSION_LABELS[key]}" for key in dimensions)
    user_prompt = render(user_template, TEXT=text, DIMENSIONS=listed)
    return system_prompt, user_prompt


def _to_dimensions(
    envelope: ModelAnalyzeEnvelope, requested: list[str]
) -> tuple[list[DimensionScore], int]:
    """逐条校验模型给的维度判断，补齐未判断的维度，返回 (维度列表, 被丢弃条数)。

    丢弃的情形：单条不合 schema（缺 judgment、confidence 越界、key 不在七维内）、
    同一个 key 重复出现（保留第一条）。

    未出现在模型输出里的 key **不算丢弃**，而是补一条 `missing: true` 的占位——
    这是"缺失不删只占位"的落点（API.md §6）。
    """
    dropped = 0
    found: dict[str, ModelDimension] = {}

    for raw in envelope.dimensions:
        try:
            dimension = ModelDimension.model_validate(raw)
        except ValidationError:
            dropped += 1
            continue
        if dimension.key in found:
            dropped += 1
            continue
        found[dimension.key] = dimension

    # 顺序固定按 DIMENSION_KEYS 走（而不是模型给的顺序）：雷达图的 7 根轴不能随数据换位置
    dimensions: list[DimensionScore] = []
    for key in DIMENSION_KEYS:
        if key not in requested:
            continue
        model_dimension = found.get(key)
        if model_dimension is None:
            dimensions.append(
                DimensionScore(
                    key=key,
                    label=DIMENSION_LABELS[key],
                    judgment=MISSING_JUDGMENT,
                    evidence=[],
                    confidence=0.0,
                    uncertain=True,
                    missing=True,
                    knowledgePoints=[],
                )
            )
            continue
        dimensions.append(
            DimensionScore(
                key=key,
                label=DIMENSION_LABELS[key],
                judgment=model_dimension.judgment,
                evidence=list(model_dimension.evidence),
                confidence=model_dimension.confidence,
                uncertain=model_dimension.uncertain,
                missing=False,
                knowledgePoints=[point for point in model_dimension.knowledgePoints if point],
            )
        )
    return dimensions, dropped


def _to_graph(
    envelope: ModelAnalyzeEnvelope,
) -> tuple[list[AnalyzeEntity], list[AnalyzeRelation], int]:
    """校验实体与关系，返回 (实体, 关系, 被丢弃条数)。

    关系的两个端点必须出现在实体表里，否则丢弃——悬空边会让知识图谱出现"无名节点"。
    实体按名字去重，关系按 (source, target, relation) 三元组去重。
    """
    dropped = 0
    entities: list[AnalyzeEntity] = []
    seen_names: set[str] = set()

    for raw in envelope.entities:
        try:
            entity = ModelEntity.model_validate(raw)
        except ValidationError:
            dropped += 1
            continue
        if entity.name in seen_names:
            dropped += 1
            continue
        seen_names.add(entity.name)
        entities.append(AnalyzeEntity(name=entity.name, kind=entity.kind, note=entity.note))

    relations: list[AnalyzeRelation] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for raw in envelope.relations:
        try:
            relation = ModelRelation.model_validate(raw)
        except ValidationError:
            dropped += 1
            continue
        if relation.source not in seen_names or relation.target not in seen_names:
            dropped += 1
            continue
        key = (relation.source, relation.target, relation.relation)
        if key in seen_edges:
            dropped += 1
            continue
        seen_edges.add(key)
        relations.append(
            AnalyzeRelation(
                source=relation.source, target=relation.target, relation=relation.relation
            )
        )

    return entities, relations, dropped


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    check_rate_limit(_client_key(request))

    text = payload.text
    if not text.strip():
        raise ApiError(INVALID_REQUEST, "待分析文本不能为空")
    if len(text) > MAX_TEXT_LEN:
        raise ApiError(TEXT_TOO_LONG, f"文本 {len(text)} 字，超过上限 {MAX_TEXT_LEN} 字")

    # dimensions 的合法性已由 AnalyzeRequest 的校验器保证（未知 key -> 400）
    requested = payload.dimensions or list(DIMENSION_KEYS)
    sampled_text, sampled = sample_text(text)

    system_prompt, user_prompt = _build_prompts(sampled_text, requested)
    result = await complete_json(
        settings=get_settings(), system_prompt=system_prompt, user_prompt=user_prompt
    )

    raw_json = extract_json_object(result.content)
    try:
        raw: Any = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ApiError(LLM_BAD_JSON, f"模型输出不是合法 JSON：{exc.msg}") from exc

    try:
        envelope = ModelAnalyzeEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise ApiError(
            LLM_BAD_JSON, f"模型输出未通过 schema 校验：{_describe_validation_error(exc)}"
        ) from exc

    dimensions, dropped_dimensions = _to_dimensions(envelope, requested)
    entities, relations, dropped_graph = _to_graph(envelope)

    return AnalyzeResponse(
        requestId=_new_request_id(),
        model=result.model,
        elapsedMs=result.elapsed_ms,
        analyzedChars=len(sampled_text),
        sampled=sampled,
        dimensions=dimensions,
        entities=entities,
        relations=relations,
        droppedCount=dropped_dimensions + dropped_graph,
    )
