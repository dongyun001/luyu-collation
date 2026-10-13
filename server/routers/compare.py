"""POST /api/v1/compare —— 版本对勘（F13 对校引擎），契约见 API.md §7。

**本端点不调用任何大模型**：没有密钥要求、没有 `LLM_*` 错误、断网可用。
它存在的意义是把"四法引擎"里的**对校**从设计落到可演示：与理校（LLM）不同，
对校给的是确定性结论，这也是 `ROADMAP §4` 里"非套壳"的硬证据。

调用链：限流 → 入参语义校验 → 字符级对齐（纯规则）→ 排序编号 → 返回。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from ..services.version_align import align_versions
from ..utils.errors import INTERNAL_ERROR, INVALID_REQUEST, TEXT_TOO_LONG, ApiError
from ..utils.rate_limit import check_rate_limit
from ..utils.request_meta import client_key, new_request_id
from ..utils.schemas import (
    MAX_REFERENCES,
    MAX_TEXT_LEN,
    CompareItem,
    CompareRequest,
    CompareResponse,
    PresenceDiffItem,
)

router = APIRouter()


def _validate(payload: CompareRequest) -> None:
    """语义校验。放在这里而不是 pydantic 里，是为了让错误码走 API.md 的
    400/`INVALID_REQUEST`、413/`TEXT_TOO_LONG`，而不是 FastAPI 默认的 422。
    """
    if not payload.baseText.strip():
        raise ApiError(INVALID_REQUEST, "底本文本不能为空")
    if len(payload.baseText) > MAX_TEXT_LEN:
        raise ApiError(
            TEXT_TOO_LONG, f"底本 {len(payload.baseText)} 字，超过上限 {MAX_TEXT_LEN} 字"
        )

    count = len(payload.references)
    if not 1 <= count <= MAX_REFERENCES:
        raise ApiError(
            INVALID_REQUEST,
            f"参照本需要 1–{MAX_REFERENCES} 个，收到 {count} 个",
        )

    names: set[str] = set()
    for index, reference in enumerate(payload.references, start=1):
        name = reference.name.strip()
        if not name:
            raise ApiError(INVALID_REQUEST, f"第 {index} 个参照本的 name 不能为空")
        if name in names:
            # 重名会让"这条异文出自哪个本子"无从分辨，直接拒绝而不是悄悄改名
            raise ApiError(INVALID_REQUEST, f"参照本 name 重复：{name}")
        names.add(name)
        if len(reference.text) > MAX_TEXT_LEN:
            raise ApiError(
                TEXT_TOO_LONG,
                f"参照本「{name}」{len(reference.text)} 字，超过上限 {MAX_TEXT_LEN} 字",
            )


@router.post("/compare", response_model=CompareResponse)
async def compare(payload: CompareRequest, request: Request) -> CompareResponse:
    check_rate_limit(client_key(request))
    _validate(payload)

    started = time.perf_counter()
    result = align_versions(
        payload.baseText,
        [(reference.name.strip(), reference.text) for reference in payload.references],
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    try:
        items = [
            CompareItem(id=index, **item.__dict__)
            for index, item in enumerate(result.items, start=1)
        ]
        presence = [PresenceDiffItem(**diff.__dict__) for diff in result.presence_diffs]
    except (TypeError, ValueError) as exc:  # pragma: no cover - 契约不符时才可能触发
        raise ApiError(INTERNAL_ERROR, f"对校结果不符合响应契约：{exc}") from exc

    return CompareResponse(
        requestId=new_request_id(),
        elapsedMs=elapsed_ms,
        items=items,
        presenceDiffs=presence,
        droppedCount=0,
    )
