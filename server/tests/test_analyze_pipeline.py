"""分析端点测试（F9）：七维返回、占位语义、丢弃计数、抽样与降级分支。

不依赖真实密钥：上游一律指向 `fake_llm_provider` 的 `fake-analyze*` 分支，
断言的是**生产代码路径**的行为（schema 校验、占位补齐、悬空边过滤），不是模型的内容质量。

运行：./.venv/Scripts/python.exe -m pytest server/tests -q
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.routers.analyze import _SAMPLE_MARKER, MISSING_JUDGMENT, sample_text
from server.tests.fake_llm_provider import FIXTURE_ANALYZE_TEXT
from server.utils import rate_limit
from server.utils.schemas import (
    ANALYZE_SAMPLE_HEAD,
    ANALYZE_SAMPLE_TAIL,
    DIMENSION_KEYS,
    MAX_TEXT_LEN,
)

ANALYZE_MODEL = "fake-analyze"


@pytest.fixture()
def analyze_client(fake_provider: str, monkeypatch: pytest.MonkeyPatch):
    """把上游模型指到 `fake-analyze` 分支的分析端点测试客户端。"""
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_BASE_URL", fake_provider)
    monkeypatch.setenv("LLM_MODEL", ANALYZE_MODEL)
    rate_limit.reset()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    rate_limit.reset()


def _analyze(client: TestClient, text: str, dimensions=None):
    payload: dict = {"text": text}
    if dimensions is not None:
        payload["dimensions"] = dimensions
    return client.post("/api/v1/analyze", json=payload)


# ---------------------------------------------------------------------------
# 抽样纯函数
# ---------------------------------------------------------------------------
def test_sample_text_keeps_short_text_intact() -> None:
    text = "子曰：学而时习之。"
    sampled, flag = sample_text(text)
    assert sampled == text
    assert flag is False


def test_sample_text_takes_head_and_tail_with_marker() -> None:
    text = "甲" * 1000 + "乙" * 1500
    sampled, flag = sample_text(text)
    assert flag is True
    assert sampled.startswith("甲" * 100)
    assert sampled.endswith("乙" * 100)
    assert _SAMPLE_MARKER in sampled
    assert len(sampled) == ANALYZE_SAMPLE_HEAD + len(_SAMPLE_MARKER) + ANALYZE_SAMPLE_TAIL


# ---------------------------------------------------------------------------
# 主链路：模型输出 -> 逐项校验 -> 占位补齐 -> 实体/关系
# ---------------------------------------------------------------------------
def test_analyze_returns_all_seven_dimensions_in_fixed_order(analyze_client: TestClient) -> None:
    response = _analyze(analyze_client, FIXTURE_ANALYZE_TEXT)
    assert response.status_code == 200
    body = response.json()

    # 轴序固定：即使模型给的顺序不同、且有两个维度没产出，返回仍是七个 key 的固定序
    assert [dimension["key"] for dimension in body["dimensions"]] == list(DIMENSION_KEYS)
    assert [dimension["label"] for dimension in body["dimensions"]][0] == "文献性质"
    assert body["sampled"] is False
    assert body["analyzedChars"] == len(FIXTURE_ANALYZE_TEXT)
    assert body["requestId"].startswith("req_")


def test_analyze_missing_dimensions_become_placeholders(analyze_client: TestClient) -> None:
    body = _analyze(analyze_client, FIXTURE_ANALYZE_TEXT).json()
    by_key = {dimension["key"]: dimension for dimension in body["dimensions"]}

    # 模型未产出的两个维度不删，而是补占位（保证雷达 7 轴齐整，且不伪造结论）
    for key in ("edition", "collation"):
        assert by_key[key]["missing"] is True
        assert by_key[key]["judgment"] == MISSING_JUDGMENT
        assert by_key[key]["confidence"] == 0.0
        assert by_key[key]["evidence"] == []
    # 有产出的维度不能被误标为 missing
    assert by_key["authorship"]["missing"] is False


def test_analyze_normalizes_confidence_and_forces_uncertain_without_evidence(
    analyze_client: TestClient,
) -> None:
    by_key = {
        dimension["key"]: dimension
        for dimension in _analyze(analyze_client, FIXTURE_ANALYZE_TEXT).json()["dimensions"]
    }
    # 百分数 72 -> 0.72（与 /collate 共用 normalize_confidence）
    assert by_key["dating"]["confidence"] == pytest.approx(0.72)
    # 无 evidence 的判断不得自称确定：强制 uncertain=True，但**不丢弃**
    assert by_key["school"]["uncertain"] is True
    assert by_key["school"]["evidence"] == []
    assert by_key["nature"]["uncertain"] is False


def test_analyze_counts_dropped_items(analyze_client: TestClient) -> None:
    body = _analyze(analyze_client, FIXTURE_ANALYZE_TEXT).json()
    # 维度 3（未知 key / 重复 key / 缺 judgment）+ 实体 2（kind 不合法 / 重名）+ 关系 2（悬空边 / 重复）
    assert body["droppedCount"] == 7


def test_analyze_filters_dangling_relations_and_dedupes_entities(
    analyze_client: TestClient,
) -> None:
    body = _analyze(analyze_client, FIXTURE_ANALYZE_TEXT).json()
    assert [entity["name"] for entity in body["entities"]] == ["孔子", "《论语》"]
    assert [entity["kind"] for entity in body["entities"]] == ["人物", "著作"]

    # 只留下端点都在实体表里的那一条关系
    assert len(body["relations"]) == 1
    relation = body["relations"][0]
    names = {entity["name"] for entity in body["entities"]}
    assert relation["source"] in names
    assert relation["target"] in names
    assert relation["relation"] == "言论被辑录于"


def test_analyze_dimension_subset_is_respected_and_ordered(analyze_client: TestClient) -> None:
    body = _analyze(analyze_client, FIXTURE_ANALYZE_TEXT, ["authorship", "dating"]).json()
    # 只返回请求的两个维度，且顺序按 DIMENSION_KEYS（dating 在 authorship 之前）
    assert [dimension["key"] for dimension in body["dimensions"]] == ["dating", "authorship"]


def test_analyze_long_text_is_sampled(analyze_client: TestClient) -> None:
    text = "子曰学而时习之，不亦说乎。" * 200  # 2600 字 > 抽样阈值 2000
    body = _analyze(analyze_client, text).json()
    assert body["sampled"] is True
    assert body["analyzedChars"] == ANALYZE_SAMPLE_HEAD + len(_SAMPLE_MARKER) + ANALYZE_SAMPLE_TAIL


# ---------------------------------------------------------------------------
# 入参校验
# ---------------------------------------------------------------------------
def test_analyze_rejects_unknown_dimension_key(analyze_client: TestClient) -> None:
    response = _analyze(analyze_client, FIXTURE_ANALYZE_TEXT, ["authorship", "不存在的维度"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_analyze_rejects_empty_text(analyze_client: TestClient) -> None:
    response = _analyze(analyze_client, "   ")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_analyze_rejects_too_long_text(analyze_client: TestClient) -> None:
    response = _analyze(analyze_client, "甲" * (MAX_TEXT_LEN + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "TEXT_TOO_LONG"


# ---------------------------------------------------------------------------
# 降级分支
# ---------------------------------------------------------------------------
def test_analyze_bad_json_returns_llm_bad_json(
    fake_provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_BASE_URL", fake_provider)
    monkeypatch.setenv("LLM_MODEL", "fake-analyze-badjson")
    rate_limit.reset()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _analyze(client, FIXTURE_ANALYZE_TEXT)
    rate_limit.reset()
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_BAD_JSON"


def test_analyze_broken_envelope_returns_llm_bad_json(
    fake_provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_BASE_URL", fake_provider)
    monkeypatch.setenv("LLM_MODEL", "fake-analyze-schemafail")
    rate_limit.reset()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = _analyze(client, FIXTURE_ANALYZE_TEXT)
    rate_limit.reset()
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_BAD_JSON"
