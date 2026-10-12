"""后端接口测试：schema 校验、原文定位、降级分支、置信度规则（TECH_DESIGN §2）。

不依赖真实大模型密钥：上游一律指向 `fake_llm_provider`（本地假模型），
因此断言的是**生产代码路径**的行为，而不是模型的内容质量。

运行：./.venv/Scripts/python.exe -m pytest server/tests -q
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic import ValidationError

from server.config import Settings
from server.main import app
from server.routers.collate import _to_collation_items
from server.services.llm import complete_json, extract_json_object
from server.services.prompt_loader import PromptError, load_prompt, render
from server.tests.fake_llm_provider import FIXTURE_SAMPLE_TEXT
from server.tests.fake_llm_provider import app as fake_app
from server.utils import rate_limit
from server.utils.errors import ApiError
from server.utils.schemas import MAX_TEXT_LEN, ModelItem, ModelOutputEnvelope

FAKE_PORT = 3099
FAKE_BASE_URL = f"http://127.0.0.1:{FAKE_PORT}/v1"


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"假模型端点未在 {timeout}s 内就绪（端口 {port}）")


@pytest.fixture(scope="session")
def fake_provider() -> str:
    """在后台线程里跑一个本地假模型，返回其 base_url。"""
    config = uvicorn.Config(fake_app, host="127.0.0.1", port=FAKE_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port(FAKE_PORT)
    yield FAKE_BASE_URL
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def client(fake_provider: str, monkeypatch: pytest.MonkeyPatch):
    """已配置好密钥与上游的测试客户端；每个用例前后清空限流计数。"""
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_BASE_URL", fake_provider)
    monkeypatch.setenv("LLM_MODEL", "fake")
    rate_limit.reset()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    rate_limit.reset()


def _collate(client: TestClient, text: str, **options):
    """未传选项时整体省略 options（与 API.md「options 可省略」一致）。"""
    payload: dict = {"text": text}
    if options:
        payload["options"] = options
    return client.post("/api/v1/collate", json=payload)


# ---------------------------------------------------------------------------
# 冒烟
# ---------------------------------------------------------------------------
def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "llmProvider": "qwen", "ocrConfigured": False}


def test_health_reports_ocr_configured_when_keys_present(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_API_KEY", "k")
    monkeypatch.setenv("OCR_SECRET_KEY", "s")
    assert client.get("/api/v1/health").json()["ocrConfigured"] is True


# ---------------------------------------------------------------------------
# 主链路：模型输出 -> 契约校验 -> 原文定位 -> 置信度修正 -> 响应
# ---------------------------------------------------------------------------
def test_collate_filters_and_normalizes_model_output(client: TestClient) -> None:
    response = _collate(client, FIXTURE_SAMPLE_TEXT, produceTranslation=True)
    assert response.status_code == 200
    body = response.json()

    # 假模型给了 8 条，其中 1 条类型不合法、1 条 suggested 与 original 相同（空操作）、
    # 1 条原文定位失败、1 条重复 -> 丢弃 4 条
    assert body["droppedCount"] == 4
    assert [item["id"] for item in body["items"]] == [1, 2, 3, 4]
    assert [item["type"] for item in body["items"]] == ["讹字", "通假", "异文", "讹字"]
    # offset 由后端按「校验后采用、校验不过退回首次出现」定位，并按升序排列
    assert [item["offset"] for item in body["items"]] == [2, 11, 14, 19]
    # 置信度经字表命中修正：代/伐、说/悦 各 +0.1 封顶 1.0；88 -> 0.88 再 +0.1；
    # 未命中字表的异文保持 0.55（前端据此折叠为低置信建议）
    assert [item["confidence"] for item in body["items"]] == [1.0, 1.0, 0.55, 0.98]
    assert body["model"] == "fake"
    assert body["translation"].startswith("联调固定译文")
    assert body["requestId"].startswith("req_")
    assert body["elapsedMs"] >= 0

    # 每条 original 都必须是原文子串（API.md §2 硬约束）
    for item in body["items"]:
        assert item["original"] in FIXTURE_SAMPLE_TEXT
        assert FIXTURE_SAMPLE_TEXT[item["offset"] : item["offset"] + len(item["original"])] == item["original"]


def test_collate_without_translation_returns_empty_string(client: TestClient) -> None:
    body = _collate(client, FIXTURE_SAMPLE_TEXT, produceTranslation=False).json()
    assert body["translation"] == ""


def test_collate_accepts_no_options_at_all(client: TestClient) -> None:
    response = client.post("/api/v1/collate", json={"text": FIXTURE_SAMPLE_TEXT})
    assert response.status_code == 200
    assert response.json()["translation"] != ""


def test_collate_accepts_explicit_null_options(client: TestClient) -> None:
    """显式 null 与省略等价，不应被打成 400。"""
    response = client.post(
        "/api/v1/collate", json={"text": FIXTURE_SAMPLE_TEXT, "options": None}
    )
    assert response.status_code == 200
    assert response.json()["translation"] != ""


def test_collate_with_text_matching_nothing_drops_everything(client: TestClient) -> None:
    body = _collate(client, "abc").json()
    assert body["items"] == []
    assert body["droppedCount"] == 8


# ---------------------------------------------------------------------------
# 条目定位与去重（2026-10-12 修订）：同一个字重复出现时，两处都该被留住并标对位置
# ---------------------------------------------------------------------------
def _model_item(offset=None) -> dict:
    """一条「代 → 伐」讹字建议；offset 为 None 时表示模型没给。"""
    item = {
        "type": "讹字",
        "original": "代",
        "suggested": "伐",
        "reason": "「伐」误作「代」，形近而讹",
        "confidence": 0.95,
    }
    if offset is not None:
        item["offset"] = offset
    return item


def test_repeated_char_keeps_both_occurrences() -> None:
    """同一个字出现两处、模型各报一条：**两条都要留**。

    旧实现把两处当成「同类型+同原文+同建议」的重复，第二处被丢弃（实测确实丢了）。
    去重键带上 offset 之后，两处才是两处。
    """
    text = "代我。代我。"
    assert [i for i, char in enumerate(text) if char == "代"] == [0, 3]

    items, dropped = _to_collation_items(
        ModelOutputEnvelope(items=[_model_item(0), _model_item(3)], translation=""),
        text,
    )

    assert dropped == 0
    assert [item.offset for item in items] == [0, 3]
    assert [item.id for item in items] == [1, 2]  # 仍是按序编号，前端据此可分别采纳


def test_model_offset_is_honored_when_it_matches() -> None:
    """模型自报的 offset 指向第二处且该处文本确实等于 original → **采用它**（不再恒为 0）。"""
    items, dropped = _to_collation_items(
        ModelOutputEnvelope(items=[_model_item(3)], translation=""), "代我。代我。"
    )
    assert dropped == 0
    assert [item.offset for item in items] == [3]


@pytest.mark.parametrize(
    ("text", "offset"),
    [
        ("代我。", 1),    # 位置合法但那里的字不是「代」（模型数错了）
        ("代我。", 99),   # 越界
        ("代我。", None),  # 模型压根没给
    ],
)
def test_invalid_or_missing_offset_falls_back_to_first_occurrence(text: str, offset) -> None:
    """校验不通过就退回首次出现——保住"防模型乱报 offset"的能力。"""
    items, dropped = _to_collation_items(
        ModelOutputEnvelope(items=[_model_item(offset)], translation=""), text
    )
    assert dropped == 0
    assert [item.offset for item in items] == [0]


# ---------------------------------------------------------------------------
# 入参校验与限流
# ---------------------------------------------------------------------------
def test_text_too_long_returns_413(client: TestClient) -> None:
    response = _collate(client, "字" * (MAX_TEXT_LEN + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "TEXT_TOO_LONG"


def test_text_at_limit_is_accepted(client: TestClient) -> None:
    assert _collate(client, "字" * MAX_TEXT_LEN).status_code == 200


def test_empty_text_returns_invalid_request(client: TestClient) -> None:
    response = _collate(client, "   ")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_text_field_uses_unified_error_format(client: TestClient) -> None:
    """FastAPI 默认的 422 详情结构必须被统一成 API.md 的 {error:{code,message}}。"""
    response = client.post("/api/v1/collate", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_invalid_check_type_is_rejected(client: TestClient) -> None:
    response = _collate(client, FIXTURE_SAMPLE_TEXT, checkTypes=["错别字"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_rate_limit_returns_429(client: TestClient) -> None:
    for _ in range(rate_limit.MAX_REQUESTS):
        assert _collate(client, FIXTURE_SAMPLE_TEXT).status_code == 200
    response = _collate(client, FIXTURE_SAMPLE_TEXT)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


# ---------------------------------------------------------------------------
# 降级分支：密钥缺失 / 上游异常 / 模型脏输出
# ---------------------------------------------------------------------------
def test_missing_api_key_returns_provider_misconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    response = _collate(client, FIXTURE_SAMPLE_TEXT)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PROVIDER_MISCONFIGURED"
    assert "LLM_API_KEY" in response.json()["error"]["message"]


def test_unreachable_upstream_returns_provider_misconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")
    response = _collate(client, FIXTURE_SAMPLE_TEXT)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PROVIDER_MISCONFIGURED"


def test_upstream_500_returns_provider_misconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL", "fake-error500")
    response = _collate(client, FIXTURE_SAMPLE_TEXT)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PROVIDER_MISCONFIGURED"
    assert "500" in response.json()["error"]["message"]


def test_non_json_model_output_returns_llm_bad_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL", "fake-badjson")
    response = _collate(client, FIXTURE_SAMPLE_TEXT)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_BAD_JSON"


def test_bad_envelope_returns_llm_bad_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL", "fake-schemafail")
    response = _collate(client, FIXTURE_SAMPLE_TEXT)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_BAD_JSON"


def _llm_settings(fake_provider: str, model: str, **overrides) -> Settings:
    """构造只指向假模型的 Settings；超时预算用小数，避免让用例真等几十秒。"""
    base = {
        "llm_provider": "qwen",
        "llm_api_key": "fake-key",
        "llm_base_url": fake_provider,
        "llm_model": model,
        "ocr_api_key": "",
        "ocr_secret_key": "",
        "port": 3001,
        "max_attempts": 1,
    }
    base.update(overrides)
    return Settings(**base)


def test_upstream_timeout_maps_to_llm_timeout(fake_provider: str) -> None:
    """连响应头都不给的上游 -> LLM_TIMEOUT（由首块宽限拦下）。"""
    settings = _llm_settings(
        fake_provider, "fake-timeout", first_token_timeout_s=1.0, request_budget_s=30.0
    )
    with pytest.raises(ApiError) as excinfo:
        asyncio.run(complete_json(settings=settings, system_prompt="s", user_prompt="u"))
    assert excinfo.value.code == "LLM_TIMEOUT"


def test_slow_but_producing_upstream_is_not_a_timeout(fake_provider: str) -> None:
    """**判据翻转用例**：边生成边吐字节的上游，即便总耗时远超阈值也必须成功。

    旧实现（60 秒硬性总时限）在这里期望超时；实测证明那是误杀——流式实测 20 余次，
    相邻增量块的最大间隔只有 4.6 秒，上游一直在产出。假模型每秒吐一块、共吐约 10 块
    （总耗时约 10 秒，远大于停滞阈值 2 秒），正好复现"慢但在动"。
    """
    settings = _llm_settings(
        fake_provider,
        "fake-dribble",
        stall_timeout_s=2.0,
        first_token_timeout_s=2.0,
        request_budget_s=60.0,
    )
    started = time.monotonic()
    result = asyncio.run(complete_json(settings=settings, system_prompt="s", user_prompt="u"))
    elapsed = time.monotonic() - started

    # 必须拿到完整正文（吐了约 10 块才结束）
    assert "联调固定译文" in result.content
    # 关键断言：我们**等**它吐完了，而不是在吞吐间隔上把它掐断。
    assert elapsed >= 5, f"没有等到流结束就返回了，耗时 {elapsed:.1f}s"


def test_silent_upstream_hits_stall_watchdog(fake_provider: str) -> None:
    """吐一块后彻底静默 -> LLM_TIMEOUT，且必须由**停滞看门狗**触发。

    假模型静默 30 秒；这里把停滞阈值设成 0.3 秒、总预算设成 10 秒。断言总耗时远小于
    静默时长与总预算，才能证明拦下它的是"没有新内容"这条判据，而不是别的兜底。
    """
    settings = _llm_settings(
        fake_provider,
        "fake-stall",
        stall_timeout_s=0.3,
        first_token_timeout_s=1.0,
        request_budget_s=10.0,
    )
    started = time.monotonic()
    with pytest.raises(ApiError) as excinfo:
        asyncio.run(complete_json(settings=settings, system_prompt="s", user_prompt="u"))
    elapsed = time.monotonic() - started

    assert excinfo.value.code == "LLM_TIMEOUT"
    assert "停滞" in excinfo.value.message
    assert elapsed < 3, f"不是停滞看门狗拦下的，耗时 {elapsed:.1f}s"


def test_stalled_attempt_is_retried_and_succeeds(fake_provider: str) -> None:
    """停滞的段会被重试；假模型奇数次调用静默、偶数次正常，所以重试应当成功。

    现状下同样的输入会直接失败（首段超时 -> 整轮报错），这是本次改动的核心收益点。
    """
    settings = _llm_settings(
        fake_provider,
        "fake-flaky",
        stall_timeout_s=0.3,
        first_token_timeout_s=1.0,
        request_budget_s=30.0,
        max_attempts=3,
        retry_backoff_s=0.0,
    )
    result = asyncio.run(complete_json(settings=settings, system_prompt="s", user_prompt="u"))
    assert "联调固定译文" in result.content


def test_exhausted_retries_report_attempt_count(fake_provider: str) -> None:
    """重试用尽后仍失败：错误消息要说明尝试了几次，便于现场定位与佐证。"""
    settings = _llm_settings(
        fake_provider,
        "fake-stall",
        stall_timeout_s=0.2,
        first_token_timeout_s=0.4,
        request_budget_s=30.0,
        max_attempts=3,
        retry_backoff_s=0.0,
    )
    with pytest.raises(ApiError) as excinfo:
        asyncio.run(complete_json(settings=settings, system_prompt="s", user_prompt="u"))
    assert excinfo.value.code == "LLM_TIMEOUT"
    assert "共尝试 3 次" in excinfo.value.message


# ---------------------------------------------------------------------------
# Prompt 资产
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["collate_v1", "translate_text_v1", "explain_v1"])
def test_prompt_assets_load(name: str) -> None:
    assert load_prompt(name)


def test_collate_prompt_renders_and_keeps_json_braces() -> None:
    """Prompt 里有 JSON 示例，渲染必须只替换 {{KEY}}，不能碰单个 `{}`。"""
    collate = load_prompt("collate_v1")
    fragment = load_prompt("translate_text_v1")["FRAGMENT"]
    user = render(
        collate["USER"],
        TEXT="北冥有鱼，其名鲲。",
        CHECK_TYPES="讹字、脱文",
        REFERENCE_EDITION="通行本",
        TRANSLATION_INSTRUCTION=fragment,
    )
    assert "北冥有鱼，其名鲲。" in user
    assert "讹字、脱文" in user
    assert '"items": [' in user  # 未提供占位符的模板必须原样保留 JSON 示例
    assert "{{" not in user


def test_render_rejects_unknown_placeholder() -> None:
    with pytest.raises(PromptError):
        render("正文 {{MISSING}}", TEXT="x")


def test_render_preserves_user_text_containing_braces() -> None:
    """用户粘贴的文本里含 {{...}} 时应原样保留，不被当成模板缺参。"""
    assert render("文：{{TEXT}}", TEXT="含 {{ABC}} 的原文") == "文：含 {{ABC}} 的原文"


# ---------------------------------------------------------------------------
# 模型原始文本 -> JSON 提取
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        '{"items": []}',
        '```json\n{"items": []}\n```',
        '好的，结果如下：\n{"items": []}\n以上。',
    ],
)
def test_extract_json_object(raw: str) -> None:
    assert extract_json_object(raw) == '{"items": []}'


def test_extract_json_object_rejects_prose() -> None:
    with pytest.raises(ApiError) as excinfo:
        extract_json_object("这里完全没有 JSON。")
    assert excinfo.value.code == "LLM_BAD_JSON"


# ---------------------------------------------------------------------------
# 输出契约：suggested 必须与 original 不同（API.md §2）
# ---------------------------------------------------------------------------
def test_schema_rejects_no_op_suggestion() -> None:
    """suggested 与 original 相同属空操作，直接判为不合契约。

    实测来源：真实模型对异文类正是这样——把别本写法只写进 reason，
    suggested 填成与底本相同。若不拦，UI 会显示「X → X」、校勘记会写出「一作 X」。
    """
    with pytest.raises(ValidationError):
        ModelItem(
            type="异文",
            original="豫章故郡",
            suggested="豫章故郡",
            reason="别本作「南昌故郡」，据通行本取「豫章」",
            confidence=0.65,
        )


def test_schema_accepts_variant_reading_as_suggested() -> None:
    """异文类把别本写法放进 suggested —— 这是 v2 契约要求的正确形态。"""
    item = ModelItem(
        type="异文",
        original="豫章故郡",
        suggested="南昌故郡",
        reason="别本作「南昌故郡」，与「洪都新府」对文，据通行本取「豫章」",
        confidence=0.65,
    )
    assert item.suggested == "南昌故郡"
    assert item.original != item.suggested


def test_collate_prompt_in_use_is_v2() -> None:
    """Prompt 换版时提醒同步改回归集与本文档；这里守住调用方引用。"""
    from server.routers.collate import COLLATE_PROMPT

    assert COLLATE_PROMPT == "collate_v2"
