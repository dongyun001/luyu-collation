"""对校引擎（F13）测试：确定性、定位、多版本归并、存缺、入参边界。

**本套测试不依赖任何模型**——这正是 /compare 与 /collate 的区别。其中一条用例
（`test_never_touches_llm`）把模型客户端替换成"一调就炸"，用来**证明**它真的没调：
断言"没报错"只是没有反例，"调用会炸但没有炸"才是证据。

运行：./.venv/Scripts/python.exe -m pytest server/tests -q
"""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.services import version_align
from server.utils import rate_limit
from server.utils.schemas import MAX_TEXT_LEN

# 《滕王阁序》开篇：字面无版权问题，且「豫章/南昌」正是异文的经典例（一本作"豫章故郡"、
# 一本作"南昌故郡"），拿它当夹具与文献学常识一致。
BASE_TEXT = "豫章故郡，洪都新府。星分翼轸，地接衡庐。"
SAME_TEXT = "南昌故郡，洪都新府。星分翼轸，地接衡庐。"
# 参照本整句脱去首四字
REFERENCE_MISSING_TEXT = "洪都新府。星分翼轸，地接衡庐。"
# 参照本多出一句
REFERENCE_EXTRA_TEXT = "豫章故郡，洪都新府，龙光射斗。星分翼轸，地接衡庐。"


@pytest.fixture()
def client() -> TestClient:
    """/compare 不需要密钥，也不该读密钥——这里刻意**不**注入任何 LLM_* 环境变量。"""
    rate_limit.reset()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    rate_limit.reset()


def _compare(client: TestClient, base: str, references: list[dict[str, str]]):
    return client.post("/api/v1/compare", json={"baseText": base, "references": references})


# ---------------------------------------------------------------------------
# 对齐本身（纯函数）
# ---------------------------------------------------------------------------
def test_single_replacement_is_one_item() -> None:
    """difflib 给的是**最小**差异块：这里报「豫章」→「南昌」而不是整块四字，这是对的。"""
    result = version_align.align_pair(BASE_TEXT, "甲本", SAME_TEXT)

    assert result.presence_diffs == []
    assert len(result.items) == 1
    item = result.items[0]
    assert (item.original, item.suggested) == ("豫章", "南昌")
    assert item.offset == 0
    assert item.type == "异文"
    assert item.confidence == 1.0
    assert item.source == "甲本"
    assert item.reason == "「甲本」作「南昌」"


def test_identical_texts_produce_nothing() -> None:
    result = version_align.align_pair(BASE_TEXT, "甲本", BASE_TEXT)
    assert result.items == []
    assert result.presence_diffs == []


def test_reference_missing_and_extra_kinds() -> None:
    missing = version_align.align_pair(BASE_TEXT, "甲本", REFERENCE_MISSING_TEXT)
    assert [diff.kind for diff in missing.presence_diffs] == ["reference-missing"]
    gone = missing.presence_diffs[0]
    assert "豫章故郡" in gone.text
    assert BASE_TEXT[gone.offset : gone.offset + len(gone.text)] == gone.text

    extra = version_align.align_pair(BASE_TEXT, "乙本", REFERENCE_EXTRA_TEXT)
    assert [diff.kind for diff in extra.presence_diffs] == ["reference-extra"]
    added = extra.presence_diffs[0]
    assert "龙光射斗" in added.text
    # extra 的 offset 是**底本**里的插入点（不是参照本里的下标）
    assert 0 <= added.offset <= len(BASE_TEXT)


def test_offset_always_points_at_base_substring() -> None:
    """不变式：每条异文的 original 必须是底本的子串，且 offset 指向它。"""
    for reference in (SAME_TEXT, REFERENCE_MISSING_TEXT, REFERENCE_EXTRA_TEXT):
        for item in version_align.align_pair(BASE_TEXT, "某本", reference).items:
            assert BASE_TEXT[item.offset : item.offset + len(item.original)] == item.original


def test_deterministic_across_calls() -> None:
    args = (BASE_TEXT, [("甲本", SAME_TEXT), ("乙本", REFERENCE_EXTRA_TEXT)])
    assert version_align.align_versions(*args) == version_align.align_versions(*args)


def test_multi_reference_merge_keeps_one_row_per_reference() -> None:
    """两个参照本命中同一处 → 各出一条（source 不同），不合并成一条。

    合并会丢掉其中一家的写法，而"甲本作南昌、乙本作洪州"恰恰是两条独立信息
    （南昌与洪州都是该地在不同时期的称法，是真实的版本差异场景）。
    """
    other = "洪州故郡，洪都新府。星分翼轸，地接衡庐。"
    result = version_align.align_versions(BASE_TEXT, [("甲本", SAME_TEXT), ("乙本", other)])

    assert [item.source for item in result.items] == ["甲本", "乙本"]
    assert [item.suggested for item in result.items] == ["南昌", "洪州"]
    assert all(item.offset == 0 for item in result.items)


def test_long_text_stays_fine_grained() -> None:
    """回归守：`autojunk` 必须保持 False。

    中文常用字在长文本里出现次数远超「popular 元素」阈值，一旦开 autojunk，
    对齐会塌成**一整块**——同一对 5000 字文本实测：False 得 57 条细粒度异文
    （最长 2 字），True 得 **1 条 4951 字的巨块**，异文等于全丢。
    """
    alphabet = "子曰学而时习之不亦说乎有朋自远方来不亦乐乎人不知而不愠君子乎"
    rng = random.Random(7)
    base = "".join(rng.choice(alphabet) for _ in range(5000))
    mutated = list(base)
    for _ in range(60):
        mutated[rng.randrange(len(mutated))] = rng.choice(alphabet)
    reference = "".join(mutated)

    result = version_align.align_pair(base, "甲本", reference)

    assert len(result.items) >= 40  # 塌成一块时会掉到 1
    assert max(len(item.original) for item in result.items) <= 20


# ---------------------------------------------------------------------------
# 端点行为
# ---------------------------------------------------------------------------
def test_compare_endpoint_ok(client: TestClient) -> None:
    response = _compare(client, BASE_TEXT, [{"name": "甲本", "text": SAME_TEXT}])
    assert response.status_code == 200

    body = response.json()
    assert set(body) == {"requestId", "elapsedMs", "items", "presenceDiffs", "droppedCount"}
    assert body["requestId"].startswith("req_")
    assert body["droppedCount"] == 0  # 无模型输出 → 恒为 0
    assert body["items"] == [
        {
            "id": 1,
            "type": "异文",
            "original": "豫章",
            "suggested": "南昌",
            "reason": "「甲本」作「南昌」",
            "offset": 0,
            "confidence": 1.0,
            "source": "甲本",
        }
    ]
    assert body["presenceDiffs"] == []


def test_merge_across_references_in_one_response(client: TestClient) -> None:
    body = _compare(
        client,
        BASE_TEXT,
        [{"name": "甲本", "text": SAME_TEXT}, {"name": "乙本", "text": REFERENCE_EXTRA_TEXT}],
    ).json()

    assert [item["id"] for item in body["items"]] == [1]  # 编号从 1 起且连续
    assert body["presenceDiffs"] == [
        {"source": "乙本", "kind": "reference-extra", "text": "，龙光射斗", "offset": 9}
    ]


def test_never_touches_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """把模型客户端换成"一调就炸"，/compare 仍须 200——这是"不调模型"的证据。"""

    async def _explode(*args, **kwargs):
        raise AssertionError("/compare 不应调用大模型")

    monkeypatch.setattr("server.services.llm.complete_json", _explode)
    monkeypatch.setattr("server.routers.collate.complete_json", _explode)
    assert _compare(client, BASE_TEXT, [{"name": "甲本", "text": SAME_TEXT}]).status_code == 200


@pytest.mark.parametrize(
    ("base", "references", "code"),
    [
        ("   ", [{"name": "甲本", "text": SAME_TEXT}], "INVALID_REQUEST"),
        (BASE_TEXT, [], "INVALID_REQUEST"),
        (BASE_TEXT, [{"name": f"本{i}", "text": SAME_TEXT} for i in range(4)], "INVALID_REQUEST"),
        (BASE_TEXT, [{"name": "  ", "text": SAME_TEXT}], "INVALID_REQUEST"),
        (
            BASE_TEXT,
            [{"name": "甲", "text": SAME_TEXT}, {"name": "甲", "text": REFERENCE_EXTRA_TEXT}],
            "INVALID_REQUEST",
        ),
        ("甲" * (MAX_TEXT_LEN + 1), [{"name": "甲本", "text": SAME_TEXT}], "TEXT_TOO_LONG"),
        (BASE_TEXT, [{"name": "甲本", "text": "甲" * (MAX_TEXT_LEN + 1)}], "TEXT_TOO_LONG"),
    ],
)
def test_validation_errors(client: TestClient, base: str, references: list[dict], code: str) -> None:
    response = client.post("/api/v1/compare", json={"baseText": base, "references": references})
    assert response.status_code == {"INVALID_REQUEST": 400, "TEXT_TOO_LONG": 413}[code]
    assert response.json()["error"]["code"] == code


def test_three_references_are_allowed(client: TestClient) -> None:
    references = [
        {"name": "甲本", "text": SAME_TEXT},
        {"name": "乙本", "text": REFERENCE_EXTRA_TEXT},
        {"name": "丙本", "text": REFERENCE_MISSING_TEXT},
    ]
    assert _compare(client, BASE_TEXT, references).status_code == 200


def test_reference_name_is_trimmed(client: TestClient) -> None:
    body = _compare(client, BASE_TEXT, [{"name": "  甲本  ", "text": SAME_TEXT}]).json()
    assert body["items"][0]["source"] == "甲本"
    assert body["items"][0]["reason"] == "「甲本」作「南昌」"


def test_compare_is_not_rate_limited_by_other_endpoints(client: TestClient) -> None:
    """限流与 /collate 共用同一个计数器（API.md §7），用满即 429。"""
    for _ in range(30):
        assert _compare(client, BASE_TEXT, [{"name": "甲本", "text": SAME_TEXT}]).status_code == 200
    response = _compare(client, BASE_TEXT, [{"name": "甲本", "text": SAME_TEXT}])
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
