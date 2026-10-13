"""POST /api/v1/collate —— 智能校勘（F2）与白话译文（F5），契约见 API.md §2。

调用链：限流 → 入参校验 → Prompt 组装 → 调模型 → 取 JSON →
逐条 schema 校验（不合契约的丢弃计 droppedCount）→ 置信度规则修正 → 排序编号。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from pydantic import ValidationError

from ..config import get_settings
from ..services import confidence as confidence_rules
from ..services.llm import complete_json, extract_json_object
from ..services.prompt_loader import COLLATE_PROMPT, TRANSLATE_PROMPT, load_prompt, render
from ..utils.errors import INTERNAL_ERROR, INVALID_REQUEST, LLM_BAD_JSON, TEXT_TOO_LONG, ApiError
from ..utils.rate_limit import check_rate_limit
from ..utils.request_meta import client_key, new_request_id
from ..utils.schemas import (
    MAX_TEXT_LEN,
    CollateRequest,
    CollateResponse,
    CollationItem,
    ModelItem,
    ModelOutputEnvelope,
)

router = APIRouter()

# produceTranslation=false 时替换掉译文子 Prompt，保持 JSON 输出形状不变
_NO_TRANSLATION_BLOCK = "本次不需要白话译文：`translation` 字段固定返回空字符串。"


def _describe_validation_error(exc: ValidationError) -> str:
    """把 pydantic 报错压成一行，便于排查模型输出的哪一项不合契约。"""
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "根"
        parts.append(f"{location}: {error.get('msg', '校验失败')}")
    return "；".join(parts)


def _build_prompts(payload: CollateRequest) -> tuple[str, str]:
    """组装 (system, user) 两条 Prompt。

    译文子 Prompt 来自 translate_text_v1.md 的 FRAGMENT 段，按 TECH_DESIGN §4 的
    「无独立翻译端点」约定拼进主调用，与校勘结果一次返回。
    """
    collate = load_prompt(COLLATE_PROMPT)
    system_prompt = collate.get("SYSTEM")
    user_template = collate.get("USER")
    if not system_prompt or not user_template:
        raise ApiError(INTERNAL_ERROR, "校勘 Prompt 资产缺少 SYSTEM 或 USER 段")

    options = payload.options
    shared = {
        "TEXT": payload.text,
        "CHECK_TYPES": "、".join(options.checkTypes),
        "REFERENCE_EDITION": options.referenceEdition,
    }
    if options.produceTranslation:
        # 译文子 Prompt 先按同一组变量渲染，再作为一段注入主 Prompt
        block = render(load_prompt(TRANSLATE_PROMPT).get("FRAGMENT", ""), **shared)
        if not block:
            raise ApiError(INTERNAL_ERROR, "译文 Prompt 资产缺少 FRAGMENT 段")
    else:
        block = _NO_TRANSLATION_BLOCK

    user_prompt = render(user_template, **shared, TRANSLATION_INSTRUCTION=block)
    return system_prompt, user_prompt


def _locate(text: str, item: ModelItem) -> int:
    """定位 `original` 在原文中的起点。

    优先采用模型自报的 `offset`，但**先校验**该位置上的文本确实等于 `original`：

    - 校验通过 → 采用。这样能区分「同一个字在文中重复出现」的情况（如「代我。代我。」的
      第二处），而旧实现一律 `text.find()` 只会标第一处、把第二处也当成第一处。
    - 校验不通过 → 退回"首次出现"。这挡住了模型常见的从 1 起数、整段偏移等错值
      （旧实现正是为了防这个才完全弃用模型 offset；现在改成"校验后采用"，
      既保住防错能力，又修掉重复字只标一处的问题）。
    """
    offset = item.offset
    if isinstance(offset, int) and 0 <= offset <= len(text) - len(item.original):
        if text[offset : offset + len(item.original)] == item.original:
            return offset
    return text.find(item.original)


def _to_collation_items(
    envelope: ModelOutputEnvelope, text: str, *, rules_enabled: bool = True
) -> tuple[list[CollationItem], int]:
    """逐条校验模型建议，返回 (可用条目, 被丢弃条数)。

    丢弃的情况与 API.md §2 一致：不合 schema（类型不在五类内、缺理由、置信度越界、
    `suggested` 与 `original` 相同的空操作）、`original` 不是原文子串、
    与已有条目重复（**同类型 + 同原文 + 同建议 + 同 offset**，四元组）。

    `rules_enabled=False` 表示走**消融**配置：跳过规则的置信度修正（EVAL §5 的对照项），
    其余全流程不变。默认 True，行为与从前一致。
    """
    dropped = 0
    seen: set[tuple[str, str, str, int]] = set()
    accepted: list[tuple[int, ModelItem]] = []

    for raw in envelope.items:
        try:
            item = ModelItem.model_validate(raw)
        except ValidationError:
            dropped += 1
            continue

        if item.original not in text:
            dropped += 1
            continue

        offset = _locate(text, item)

        # 去重键必须带上 offset：同一个字在文中重复出现时，两处是各自独立的校勘点，
        # 不带位置会把第二处误判为"重复"而丢弃（旧实现的问题）。
        key = (item.type, item.original, item.suggested, offset)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)

        corrected = confidence_rules.correct_confidence(item) if rules_enabled else item
        accepted.append((offset, corrected))

    accepted.sort(key=lambda pair: pair[0])
    items = [
        CollationItem(
            id=index,
            type=item.type,
            original=item.original,
            suggested=item.suggested,
            reason=item.reason,
            confidence=item.confidence,
            offset=offset,
        )
        for index, (offset, item) in enumerate(accepted, start=1)
    ]
    return items, dropped


@router.post("/collate", response_model=CollateResponse)
async def collate(payload: CollateRequest, request: Request) -> CollateResponse:
    check_rate_limit(client_key(request))

    text = payload.text
    if not text.strip():
        raise ApiError(INVALID_REQUEST, "待校勘文本不能为空")
    if len(text) > MAX_TEXT_LEN:
        raise ApiError(TEXT_TOO_LONG, f"文本 {len(text)} 字，超过上限 {MAX_TEXT_LEN} 字")

    settings = get_settings()
    system_prompt, user_prompt = _build_prompts(payload)
    result = await complete_json(
        settings=settings, system_prompt=system_prompt, user_prompt=user_prompt
    )

    raw_json = extract_json_object(result.content)
    try:
        raw: Any = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ApiError(LLM_BAD_JSON, f"模型输出不是合法 JSON：{exc.msg}") from exc

    try:
        envelope = ModelOutputEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise ApiError(
            LLM_BAD_JSON, f"模型输出未通过 schema 校验：{_describe_validation_error(exc)}"
        ) from exc

    items, dropped = _to_collation_items(
        envelope, text, rules_enabled=settings.collate_rules_enabled
    )
    translation = envelope.translation if payload.options.produceTranslation else ""

    return CollateResponse(
        requestId=new_request_id(),
        model=result.model,
        elapsedMs=result.elapsed_ms,
        items=items,
        translation=translation,
        droppedCount=dropped,
    )
