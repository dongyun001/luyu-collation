"""标注自检测试 —— EVAL §9 前三条的"可执行版本"本身也要被测。

每条用例针对一个**会被悄悄漏掉**的错误：区间错位、类型写错、异文填成底本写法、
配额不足、以及用了 Prompt few-shot 的片段当语料。这些错误不报错、只污染结论，
所以必须由脚本拦住。
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.self_check import (
    FEWSHOT_MARKERS,
    MIN_CASE_CHARS,
    check_dataset,
)

BASE_TEXT = "十年春，齐师代我。公将战，曹刿请见。" * 12  # ≥200 字，供长度检查通过


def case(text: str = BASE_TEXT, cid: str = "c1") -> dict:
    return {"id": cid, "source": text, "origin": "夹具"}


def label(text: str = BASE_TEXT, *, start: int = 0, length: int = 1, type_: str = "讹字", **overrides) -> dict:
    start = 0 if start is None else start
    payload = {
        "id": overrides.pop("id", f"p{start}"),
        "caseId": "c1",
        "start": start,
        "end": start + length,
        "original": text[start : start + length],
        "expectedSuggestion": "〇",
        "type": type_,
        "path": ["形近"],
        "hasEditionEditionEvidence": True,
        "hasEditionEvidence": True,
        "source": "injected",
        "note": "",
    }
    payload.update(overrides)
    return payload


def errors(problems) -> list:
    return [p for p in problems if p.level == "error"]


def test_clean_minimal_dataset_has_no_errors() -> None:
    # 只给 1 个点 → 配额会报错；这里只验证"结构类"检查不误报
    problems = errors(check_dataset([case()], [label()]))
    assert all("配额" in p.where for p in problems), [vars(p) for p in problems]


def test_short_case_is_rejected() -> None:
    problems = errors(check_dataset([case(text="十年春。")], [label(text="十年春。")]))
    assert any("EVAL §2.1" in p.message for p in problems)


def test_interval_offset_mismatch_is_rejected() -> None:
    bad = label()
    bad["original"] = "错字"  # 与 text[start:end] 不一致
    problems = errors(check_dataset([case()], [bad]))
    assert any("区间错位" in p.message for p in problems)


def test_out_of_range_interval_is_rejected() -> None:
    bad = label()
    bad["start"], bad["end"] = len(BASE_TEXT) - 1, len(BASE_TEXT) + 5
    problems = errors(check_dataset([case()], [bad]))
    assert any("越界" in p.message for p in problems)


def test_unknown_type_is_rejected() -> None:
    problems = errors(check_dataset([case()], [label(type_="错字")]))
    assert any("不在五类内" in p.message for p in problems)


def test_bad_source_is_rejected() -> None:
    problems = errors(check_dataset([case()], [label(source="guessed")]))
    assert any("source" in p.message for p in problems)


def test_non_boolean_evidence_flag_is_rejected() -> None:
    problems = errors(check_dataset([case()], [label(hasEditionEvidence="yes")]))
    assert any("必须是布尔值" in p.message for p in problems)


def test_yiwen_must_not_repeat_base_writing() -> None:
    """异文类的 expectedSuggestion 必须是**别本写法**——与 API.md §2 / collate_v2 同一条契约。"""
    bad = label(type_="异文")
    assert bad["expectedSuggestion"] != bad["original"]  # 默认值不同
    bad["expectedSuggestion"] = bad["original"]
    problems = errors(check_dataset([case()], [bad]))
    assert any("别本写法" in p.message for p in problems)


def test_overlapping_gt_spans_are_rejected() -> None:
    text = BASE_TEXT
    first = label(text, start=10, length=4, id="a")
    second = label(text, start=12, length=4, id="b")  # 与 a 重叠
    problems = errors(check_dataset([case()], [first, second]))
    assert any("区间重叠" in p.message for p in problems)


def test_label_with_unknown_case_is_rejected() -> None:
    orphan = label()
    orphan["caseId"] = "c-missing"
    problems = errors(check_dataset([case()], [orphan]))
    assert any("不存在" in p.message for p in problems)


def test_duplicate_case_id_is_rejected() -> None:
    problems = errors(check_dataset([case(), case()], []))
    assert any("id 重复" in p.message for p in problems)


def test_label_without_id_is_rejected() -> None:
    """标注缺 id 必须在这里拦住。

    judge 拿 `gt["id"]` 当字典键（结果明细、复核清单都按 pointId 对齐），
    缺 id 时判定阶段会以 KeyError 崩掉，而报错信息与"少填了 id"毫无关系——
    那时已经跑完模型调用、白花了额度，所以自检必须提前报出来。
    """
    problems = errors(check_dataset([case()], [label(id=None)]))
    assert any("缺 id" in p.message for p in problems)


def test_duplicate_label_id_is_rejected() -> None:
    problems = errors(check_dataset([case()], [label(start=0, id="dup"), label(start=5, id="dup")]))
    assert any("id 重复：dup" in p.message for p in problems)


def test_fewshot_contamination_is_rejected() -> None:
    """EVAL §2.1：评测语料必须避开 Prompt 的 few-shot，否则指标失真。"""
    contaminated = "子曰：" + FEWSHOT_MARKERS[0] + "？" * 100
    problems = errors(check_dataset([case(text=contaminated)], [label(text=contaminated)]))
    assert any("few-shot" in p.message for p in problems)


def test_quota_shortfall_is_reported_per_type() -> None:
    labels = [label(start=i, id=f"p{i}") for i in range(5)]  # 只有 5 个讹字
    problems = errors(check_dataset([case()], labels))
    messages = " | ".join(p.message for p in problems)
    assert "总量 5 < 60" in messages
    assert "「衍文」只有 0 个" in messages


def test_source_field_records_provenance() -> None:
    """`source` 必须是三选一（ocr / injected / inherent）——它是"错误从哪来"的唯一记录。"""
    for value in ("ocr", "injected", "inherent"):
        problems = errors(check_dataset([case()], [label(source=value)]))
        assert not any("source" in p.message for p in problems), value


def test_self_check_marks_unverifiable_human_step_as_warning() -> None:
    """「第二人抽复核 ≥20%」机器验不了，必须留一条 warn 提醒写进报告，而不是假装检查过了。"""
    problems = check_dataset([case()], [label()])
    warns = [p for p in problems if p.level == "warn"]
    assert any("复核" in p.message for p in warns)


def test_dataset_files_roundtrip(tmp_path: Path) -> None:
    """两边都是 JSON 数组——这是 self_check / judge / run_compare 共同的输入约定。"""
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "cases.json").write_text(json.dumps([case()], ensure_ascii=False), encoding="utf-8")
    (dataset / "labels.json").write_text(json.dumps([label()], ensure_ascii=False), encoding="utf-8")
    assert len(json.loads((dataset / "cases.json").read_text(encoding="utf-8"))) == 1
    assert MIN_CASE_CHARS <= len(BASE_TEXT)
