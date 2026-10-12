"""大模型客户端：OpenAI 兼容接口，qwen 主用 / deepseek 备用（HANDOFF §5）。

两个 provider 都走 POST {base_url}/chat/completions，切换只靠环境变量，
演示时单点故障可一键切走。密钥只在此处使用，永不出现在响应里。

**超时判据是「上游是否还在产出」，不是「总耗时」**（PRD §4、TECH_DESIGN §4）：
调用走流式，逐块读取并对每一块套停滞看门狗——只要还在吐字，哪怕很慢也不算失败。
原设计是 60 秒硬性总时限，实测会误杀正常调用：流式实测 20 余次，相邻增量块的
最大间隔只有 4.6 秒、中位 0.10 秒，上游一直在产出（单次成功样本达 62 秒）；
而同一段 100 字文本三次尝试分别是 10.1s / 36.8s / 60.4s（极端到 253s），
长尾无界，调大总时限数字堵不住。

上游失败的错误码映射（API.md 的错误码表没有覆盖「上游 5xx」这类情况，
这里统一归到 PROVIDER_MISCONFIGURED，即「模型通道当前不可用」，
消息里带上游状态码与响应摘要，便于现场定位）：
  - 停滞/超预算           -> LLM_TIMEOUT (504)
  - 缺密钥/未知 provider   -> PROVIDER_MISCONFIGURED (500)
  - 其它上游/网络失败       -> PROVIDER_MISCONFIGURED (500)
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

import httpx

from ..config import Settings
from ..utils.errors import LLM_BAD_JSON, LLM_TIMEOUT, PROVIDER_MISCONFIGURED, ApiError

# 上游错误响应回填给开发者的最大长度
_BODY_EXCERPT = 300
# 低温采样：校勘要可复现、少发挥
_TEMPERATURE = 0.2
# 建连/发请求/取连接的单项超时；"上游有多慢"由停滞看门狗与尝试上限负责
_CONNECT_TIMEOUT_S = 10.0

_STATUS_HINTS = {
    401: "API Key 无效或未授权",
    403: "API Key 无权访问该模型",
    404: "接口地址或模型名不存在",
    429: "上游配额或频率受限",
}


@dataclass(frozen=True)
class LLMResult:
    """一次模型调用的结果。

    ``elapsed_ms`` 是**整个请求**的墙钟耗时（含重试），因为那才是用户实际等待的时间。
    """

    content: str
    model: str
    elapsed_ms: int


def extract_json_object(content: str) -> str:
    """从模型返回的文本里取出 JSON 对象字面量。

    模型常把 JSON 包在 ```json 围栏里，或在前后加一句客套话。这里只做「取最外层的
    {...}」这一件事 —— 取出来的内容仍要过 pydantic 校验，所以放宽提取不会放过脏数据。
    """
    text = content.strip()
    if text.startswith("```"):
        # 去掉 ```json / ``` 开头的围栏与结尾围栏
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -len("```")]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ApiError(LLM_BAD_JSON, "大模型返回的内容里找不到 JSON 对象")
    return text[start : end + 1]


def _describe_upstream_failure(status_code: int, body: str) -> str:
    text = " ".join((body or "").split())
    if len(text) > _BODY_EXCERPT:
        text = text[:_BODY_EXCERPT] + "…"
    hint = _STATUS_HINTS.get(status_code, "上游服务异常")
    return f"{hint}（HTTP {status_code}）：{text or '无响应体'}"


def _stall_message(settings: Settings, waiting_first: bool) -> str:
    """停滞/超时的用户可见说明。

    语义与 LLM_TIMEOUT 的新定义对齐：说的是"没有新内容"，不是"太慢"。
    """
    if waiting_first:
        return f"大模型无响应：{int(settings.first_token_timeout_s)} 秒内没有返回任何内容"
    return f"大模型连接停滞：{int(settings.stall_timeout_s)} 秒内没有新内容产出"


def _budget_message(budget_s: float) -> str:
    """总预算用尽时的说明（不是"太慢"，而是"预算到顶"）。"""
    return f"大模型单次请求超过 {int(budget_s)} 秒预算"


def _build_payload(settings: Settings, system_prompt: str, user_prompt: str, *, force_json: bool) -> dict:
    payload: dict = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": _TEMPERATURE,
        # 流式：这样才能逐块判"是否还在产出"。末尾会带 usage 的块，这里用不到，忽略即可。
        "stream": True,
    }
    if force_json:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _is_event_stream(response: httpx.Response) -> bool:
    return "text/event-stream" in (response.headers.get("content-type") or "")


async def _read_text(response: httpx.Response) -> str:
    return (await response.aread()).decode("utf-8", errors="replace")


async def _read_stream(response: httpx.Response, settings: Settings) -> tuple[str, str]:
    """逐块读取 SSE，返回 (正文, 模型名)。

    每个块都用 ``asyncio.wait_for`` 单独限时：首块给 ``first_token_timeout_s``（预填充阶段
    静默更长），之后给 ``stall_timeout_s``。这里不用 httpx 的 read timeout 来判停滞，是因为
    它只有一个阈值、无法区分"首块"与"增量"，而且表现不易在测试里直接断言。
    """
    parts: list[str] = []
    model = settings.llm_model
    waiting_first = True
    lines = response.aiter_lines()
    while True:
        allowance = settings.first_token_timeout_s if waiting_first else settings.stall_timeout_s
        try:
            line = await asyncio.wait_for(lines.__anext__(), timeout=allowance)
        except StopAsyncIteration:
            break
        except TimeoutError as exc:
            raise ApiError(LLM_TIMEOUT, _stall_message(settings, waiting_first)) from exc

        line = line.strip()
        if not line.startswith("data:"):
            continue  # 空行、": keepalive" 之类，不算产出
        waiting_first = False
        body = line[len("data:") :].strip()
        if body == "[DONE]":
            break
        try:
            chunk = json.loads(body)
        except ValueError:
            # 上游偶发的半截行：跳过。正文最终要过 schema 校验，这里放宽不会放过脏数据。
            continue
        if isinstance(chunk.get("model"), str):
            model = chunk["model"]
        for choice in chunk.get("choices") or []:
            # reasoning_content 只丢弃、不进正文——思考内容不属于校勘结果。
            text = (choice.get("delta") or {}).get("content")
            if isinstance(text, str) and text:
                parts.append(text)

    content = "".join(parts)
    if not content.strip():
        raise ApiError(LLM_BAD_JSON, "大模型返回了空内容")
    return content, model


def _parse_envelope(text: str, settings: Settings) -> tuple[str, str]:
    """非流式回退路径：解析一次性返回的 chat.completion 信封。"""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ApiError(PROVIDER_MISCONFIGURED, "大模型服务返回的不是 JSON 响应") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ApiError(
            PROVIDER_MISCONFIGURED, f"大模型响应结构异常：{json.dumps(data, ensure_ascii=False)[:200]}"
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise ApiError(LLM_BAD_JSON, "大模型返回了空内容")

    model = data.get("model") if isinstance(data.get("model"), str) else settings.llm_model
    return content, model


async def _call_once(
    *,
    settings: Settings,
    url: str,
    headers: dict,
    system_prompt: str,
    user_prompt: str,
    attempt_budget_s: float,
) -> tuple[str, str]:
    """一次尝试：流式调用 + 停滞看门狗；返回 (正文, 模型名)。

    ``attempt_budget_s`` 是本次尝试可用的**剩余总预算**——有意让它能用满整个预算：
    慢但持续产出的调用本来就该让它跑完，只有停滞/首块超时才会提前放弃。
    """
    try:
        async with asyncio.timeout(attempt_budget_s):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=_CONNECT_TIMEOUT_S,
                    read=attempt_budget_s,
                    write=_CONNECT_TIMEOUT_S,
                    pool=_CONNECT_TIMEOUT_S,
                )
            ) as client:
                for force_json in (True, False):
                    payload = _build_payload(
                        settings, system_prompt, user_prompt, force_json=force_json
                    )
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        # 少数 OpenAI 兼容端点不认 response_format，直接 400；
                        # Prompt 本身已强约束 JSON 输出，去掉该参数重试一次即可兼容。
                        if response.status_code == 400 and force_json:
                            body = await _read_text(response)
                            if "response_format" in body:
                                continue
                            raise ApiError(
                                PROVIDER_MISCONFIGURED,
                                _describe_upstream_failure(response.status_code, body),
                            )
                        if response.status_code >= 400:
                            raise ApiError(
                                PROVIDER_MISCONFIGURED,
                                _describe_upstream_failure(
                                    response.status_code, await _read_text(response)
                                ),
                            )
                        if _is_event_stream(response):
                            return await _read_stream(response, settings)
                        # 端点不支持流式（返回普通 JSON）：退化到一次性读取，
                        # 此时由 httpx 的 read timeout（= 本次尝试预算）兜底。
                        return _parse_envelope(await _read_text(response), settings)
    except TimeoutError as exc:
        # asyncio.timeout 触发（Python 3.11 起 asyncio.TimeoutError 即内置 TimeoutError）。
        # 注意：看门狗抛的是 ApiError，不会被这里接住，所以走到这里的只可能是预算用尽。
        raise ApiError(LLM_TIMEOUT, _budget_message(attempt_budget_s)) from exc
    except httpx.TimeoutException as exc:
        raise ApiError(LLM_TIMEOUT, _budget_message(attempt_budget_s)) from exc
    except httpx.HTTPError as exc:
        raise ApiError(PROVIDER_MISCONFIGURED, f"无法连接大模型服务：{exc}") from exc


async def complete_json(
    *,
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
) -> LLMResult:
    """调用模型并返回其原始文本（JSON 解析与 schema 校验交给调用方）。

    只对 ``LLM_TIMEOUT`` 重试：``LLM_BAD_JSON`` 与 ``PROVIDER_MISCONFIGURED`` 重试只会
    重复同样的结果/掩盖真实配置问题。重试发生在**一个请求内**，因此既不额外消耗限流额度
    （限流按 HTTP 请求计），也不改变前后端契约。
    """
    if not settings.llm_configured:
        raise ApiError(
            PROVIDER_MISCONFIGURED,
            "未配置大模型密钥：请在 .env 中填写 LLM_API_KEY（可参考 .env.example）",
        )

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    max_attempts = max(1, int(settings.max_attempts))
    attempts_made = 0
    last_error: ApiError | None = None

    for attempt in range(1, max_attempts + 1):
        remaining = settings.request_budget_s - (time.perf_counter() - started)
        if remaining <= 0:
            break  # 总预算已用尽，再派尝试也是白等
        attempts_made = attempt
        try:
            content, model = await _call_once(
                settings=settings,
                url=url,
                headers=headers,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                attempt_budget_s=remaining,
            )
        except ApiError as exc:
            if exc.code != LLM_TIMEOUT:
                raise
            last_error = exc
            if attempt >= max_attempts:
                break
            backoff = settings.retry_backoff_s * (2 ** (attempt - 1))
            # 退避之后还得留得出下一次尝试，否则不如直接把错误报给用户
            if (time.perf_counter() - started) + backoff >= settings.request_budget_s:
                break
            await asyncio.sleep(backoff)
            continue

        return LLMResult(
            content=content,
            model=model,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    message = _stall_message(settings, waiting_first=True)
    if last_error is not None:
        message = last_error.message
    if attempts_made > 1:
        message = f"{message}；已自动重试，共尝试 {attempts_made} 次仍未成功"
    raise ApiError(LLM_TIMEOUT, message) from last_error
