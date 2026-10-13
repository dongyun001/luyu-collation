"""判定器测试 —— EVAL §3 的四条口径逐条钉死。

偏移全部用 `text.index(...)` 现算，**不手数下标**：手写的区间一旦错一位，
测试会"通过"但判的是另一件事，那比没有测试更糟。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.judge import (
    HIGH_CONFIDENCE,
    judge_case,
    judge_dataset,
    load_review,
    match_case,
    overlap_length,
    is_hit_candidate,
    write_points_csv,
)

# 公有领域选段（《左传·曹刿论战》），仅作测试夹具，**不是**评测基准语料
TEXT = (
    "十年春，齐师代我。公将战，曹刿请见。其乡人曰：「肉食者谋之，又何间焉？」刿曰：「肉食者鄙，未能远谋。」"
    "乃入见。问：「何以战？」公曰：「衣食所安，弗敢专也，必以分人。」对曰：「小惠未遍，民弗从也。」"
    "公曰：「牺牲玉帛，弗敢加也，必以信。」对曰：「小信未孚，神弗福也。」"
)


def at(fragment: str) -> int:
    """片段在测试文本中的下标。"""
    return TEXT.index(fragment)


def gt(fragment: str, *, type_: str = "讹字", suggestion: str = "〇", evidence: bool = True, gid: str = "p1") -> dict:
    start = at(fragment)
    return {
        "id": gid,
        "caseId": "case-001",
        "start": start,
        "end": start + len(fragment),
        "original": fragment,
        "expectedSuggestion": suggestion,
        "type": type_,
        "path": ["形近"],
        "hasEditionEvidence": evidence,
        "source": "injected",
        "note": "",
    }


def item(fragment: str, *, type_: str = "讹字", suggestion: str = "〇", confidence: float = 0.9, iid: int = 1) -> dict:
    return {
        "id": iid,
        "type": type_,
        "original": fragment,
        "suggested": suggestion,
        "reason": "夹具",
        "confidence": confidence,
        "offset": at(fragment),
    }


# --------------------------------------------------------------------- 区间工具
def test_overlap_length_basic() -> None:
    assert overlap_length((0, 5), (3, 8)) == 2
    assert overlap_length((0, 5), (5, 9)) == 0
    assert overlap_length((3, 8), (0, 5)) == 2  # 对称


def test_hit_requires_half_of_smaller_span() -> None:
    # GT「代我」2 字，建议「代」1 字 → 重叠 1，min=1，50% → 命中
    assert is_hit_candidate(item("代", iid=1), gt("代我")) is True
    # 建议只蹭到 1 个字、而两者都长：重叠不足 50% → 不算命中（跨字误配）
    assert is_hit_candidate(item("人", iid=2), gt("曹刿请见")) is False


def test_adjacent_spans_do_not_overlap() -> None:
    assert is_hit_candidate(item("曹刿", iid=3), gt("请见")) is False


# --------------------------------------------------------------------- 匹配分配
def test_one_gt_matched_only_once_others_counted_as_duplicate() -> None:
    gts = [gt("代我", gid="p1")]
    items = [item("代我", confidence=0.95, iid=1), item("代我", confidence=0.9, iid=2)]
    result = match_case("case-001", items, gts)
    assert len(result.matches) == 1
    assert len(result.duplicates) == 1  # 另一条与已命中的 GT 重叠 → 重复，不是 FP
    assert result.unmatched_items == []


def test_one_item_matches_at_most_one_gt_taking_largest_overlap() -> None:
    gts = [gt("代我", gid="p1"), gt("齐师代我", gid="p2")]
    # 建议覆盖「齐师代我」→ 与两段 GT 都重叠，但应只算命中重叠更大的那一个
    items = [item("齐师代我", iid=1)]
    result = match_case("case-001", items, gts)
    assert len(result.matches) == 1
    assert result.matches[0][1]["id"] == "p2"


def test_unmatched_item_is_fp_before_review() -> None:
    judged = judge_case(match_case("case-001", [item("牺牲玉帛", suggestion="牺牲帛", iid=1)], [gt("代我")]))
    assert judged["rows"]["fp"] == 1
    assert judged["rows"]["extraValid"] == 0
    assert judged["detail"][-1]["verdict"] == "unreviewed"


def test_extra_valid_after_review_is_not_fp() -> None:
    matched = match_case("case-001", [item("牺牲玉帛", suggestion="牺牲帛", iid=7)], [gt("代我")])
    judged = judge_case(matched, review={"7": "extra-valid"})
    assert judged["rows"]["fp"] == 0
    assert judged["rows"]["extraValid"] == 1


def test_extra_invalid_counts_as_fp() -> None:
    matched = match_case("case-001", [item("牺牲玉帛", suggestion="牺牲帛", iid=7)], [gt("代我")])
    judged = judge_case(matched, review={"7": "extra-invalid"})
    assert judged["rows"]["fp"] == 1
    assert judged["rows"]["extraInvalid"] == 1


def test_out_of_scope_is_neither_tp_nor_fp() -> None:
    matched = match_case("case-001", [item("牺牲玉帛", suggestion="牺牲帛", iid=7)], [gt("代我")])
    judged = judge_case(matched, review={"7": "out-of-scope"})
    assert judged["rows"]["fp"] == 0
    assert judged["rows"]["outOfScope"] == 1


# --------------------------------------------------------------------- 检出与分类分开
def test_hit_but_wrong_type_still_counts_as_detection() -> None:
    gts = [gt("代我", type_="讹字", gid="p1")]
    items = [item("代我", type_="通假", iid=1)]  # 类型判错
    rows = judge_case(match_case("case-001", items, gts))["rows"]
    assert rows["tp"] == 1  # 检出算命中（§3.2）
    assert rows["typeCorrect"] == 0


def test_suggestion_accuracy_tracks_expected_suggestion() -> None:
    gts = [gt("代我", suggestion="伐我", gid="p1")]
    right = judge_case(match_case("c", [item("代我", suggestion="伐我", iid=1)], gts))["rows"]
    wrong = judge_case(match_case("c", [item("代我", suggestion="戍我", iid=1)], gts))["rows"]
    assert right["suggestionCorrect"] == 1 and right["typeCorrect"] == 1
    assert wrong["suggestionCorrect"] == 0 and wrong["typeCorrect"] == 1


def test_missing_gt_becomes_fn() -> None:
    rows = judge_case(match_case("case-001", [], [gt("代我")]))["rows"]
    assert rows["fn"] == 1
    assert rows["tp"] == 0


# --------------------------------------------------------------------- 存疑（§3.5）
def test_no_edition_evidence_is_uncertain_not_tp_not_fp() -> None:
    gts = [gt("代我", evidence=False, gid="p1")]
    rows = judge_case(match_case("case-001", [item("代我", iid=1)], gts))["rows"]
    assert rows["uncertain"] == 1
    assert rows["tp"] == 0
    assert rows["fp"] == 0


def test_unreported_uncertain_point_is_not_fn() -> None:
    rows = judge_case(match_case("case-001", [], [gt("代我", evidence=False)]))["rows"]
    assert rows["fn"] == 0
    assert rows["uncertain"] == 1


# --------------------------------------------------------------------- 指标与分层
def test_metrics_arithmetic() -> None:
    gts = [gt("代我", gid="p1"), gt("曹刿", gid="p2")]
    items = [item("代我", iid=1), item("牺牲玉帛", suggestion="牺牲帛", iid=2)]
    judged = judge_dataset(
        _write_dataset(gts),
        {"label": "t", "model": "m", "promptVersion": "collate_v2", "rulesEnabled": True,
         "cases": [{"caseId": "case-001", "items": items, "droppedCount": 3}]},
    )
    all_rows = judged["summary"]["all"]
    assert all_rows["tp"] == 1 and all_rows["fn"] == 1 and all_rows["fp"] == 1
    assert all_rows["precision"] == 0.5
    assert all_rows["recall"] == 0.5
    assert all_rows["f1"] == 0.5
    # 含 extra-valid 的 precision 在"没有 extra-valid"时与普通 precision 相同
    assert all_rows["precisionWithExtraValid"] == all_rows["precision"]


def test_layering_high_confidence_recall_not_higher_than_all() -> None:
    gts = [gt("代我", gid="p1"), gt("曹刿", gid="p2")]
    items = [item("代我", confidence=0.95, iid=1), item("曹刿", confidence=0.5, iid=2)]
    judged = judge_dataset(
        _write_dataset(gts),
        {"label": "t", "model": "m", "promptVersion": "collate_v2", "rulesEnabled": True,
         "cases": [{"caseId": "case-001", "items": items, "droppedCount": 0}]},
    )
    assert judged["summary"]["all"]["recall"] == 1.0
    # 低置信那条被分到"全部返回"层：高置信层只剩 1 条命中 → recall 0.5
    assert judged["summary"]["highConfidence"]["recall"] == 0.5
    assert HIGH_CONFIDENCE == 0.7


def test_per_type_counts_and_type_accuracy() -> None:
    gts = [gt("代我", type_="讹字", gid="p1"), gt("曹刿", type_="通假", gid="p2")]
    items = [item("代我", type_="讹字", iid=1)]  # 只报出讹字那条
    judged = judge_dataset(
        _write_dataset(gts),
        {"label": "t", "model": "m", "promptVersion": "collate_v2", "rulesEnabled": True,
         "cases": [{"caseId": "case-001", "items": items, "droppedCount": 0}]},
    )
    assert judged["perType"]["讹字"]["recall"] == 1.0
    assert judged["perType"]["讹字"]["typeAccuracy"] == 1.0
    assert judged["perType"]["通假"]["recall"] == 0.0


# --------------------------------------------------------------------- 复核清单与 CSV
def test_review_csv_roundtrip(tmp_path: Path) -> None:
    review_path = tmp_path / "review.csv"
    # 9 列：reason 与 confidence 留空，verdict 填裁决值（列数必须与表头一致，否则字段会错位）
    review_path.write_text(
        "caseId,kind,refId,original,suggested,reason,confidence,verdict,note\n"
        "case-001,unmatched-item,7,牺牲玉帛,牺牲帛,,,extra-valid,确有依据\n"
        "case-001,unmatched-item,8,肉食者,肉食,,,,未裁决\n",
        encoding="utf-8",
    )
    review = load_review(review_path)
    assert review == {"7": "extra-valid"}  # 空 verdict 的不进映射


def test_review_csv_written_by_us_can_be_read_back(tmp_path: Path) -> None:
    """`write_review_csv` 的列与 `load_review` 的读法必须自洽——否则"填完导回来"这一步会静默失效。"""
    from eval.judge import write_review_csv

    dataset_dir = _write_dataset([gt("代我", gid="p1")], tmp_path=tmp_path)
    judged = judge_dataset(
        dataset_dir,
        {"label": "t", "model": "m", "promptVersion": "collate_v2", "rulesEnabled": True,
         "cases": [{"caseId": "case-001", "items": [item("牺牲玉帛", suggestion="牺牲帛", iid=9)], "droppedCount": 0}]},
    )
    out = tmp_path / "review.csv"
    write_review_csv(out, [judged])
    rows = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2  # 表头 + 1 条待复核

    # 人工在最后一列填上裁决值（verdict）与备注（note），再读回
    header, data = rows[0], rows[1]
    filled = f"{header}\n{data.rstrip(',')},extra-valid,复核通过\n"
    fill_path = tmp_path / "review_filled.csv"
    fill_path.write_text(filled, encoding="utf-8")
    assert load_review(fill_path) == {"9": "extra-valid"}


def test_points_csv_has_one_row_per_gt_plus_extras(tmp_path: Path) -> None:
    dataset_dir = _write_dataset([gt("代我", gid="p1"), gt("曹刿", gid="p2")], tmp_path=tmp_path)
    judged = judge_dataset(
        dataset_dir,
        {"label": "t", "model": "m", "promptVersion": "collate_v2", "rulesEnabled": True,
         "cases": [{"caseId": "case-001", "items": [item("代我", iid=1), item("牺牲玉帛", suggestion="牺牲帛", iid=7)],
                    "droppedCount": 2}]},
        review={"7": "extra-valid"},
    )
    out = tmp_path / "points.csv"
    write_points_csv(out, judged, dataset_dir)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("model,promptVersion,rulesEnabled,caseId,pointId,")
    body = lines[1:]
    assert len(body) == 3  # 2 个 GT + 1 条 extra-valid
    assert any("extra:7" in line for line in body)
    assert "unreviewed" not in "\n".join(body)  # 已复核的不该再出现在未复核行


def _write_dataset(labels: list[dict], tmp_path: Path | None = None) -> Path:
    """把单段语料+标注落到临时目录，返回 dataset_dir。"""
    base = tmp_path if tmp_path is not None else Path(__file__).parent / "_tmp_dataset"
    case_dir = Path(base) / "dataset"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "cases.json").write_text(
        json.dumps([{"id": "case-001", "source": TEXT, "origin": "夹具"}], ensure_ascii=False), encoding="utf-8"
    )
    (case_dir / "labels.json").write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    return case_dir


@pytest.fixture(autouse=True)
def _cleanup_tmp() -> None:
    yield
    tmp = Path(__file__).parent / "_tmp_dataset"
    if tmp.exists():
        for path in sorted(tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        tmp.rmdir()
