"""标记 → 标注工具测试（阶段 1 补充）。

重点守两件事：
  ① **索引算对**——手数索引是标注里唯一的系统性错误来源，算错一位整份数字失真；
  ② **去标记后的 source 与原标记文件逐字对应**——`cases.json` 里的 source 与索引是对
     同一份字符串算的，两者一旦不一致，全部区间作废。
另守一条诚实性默认值：异文没写别本依据时 `hasEditionEvidence` 自动 false，而不是乐观地给 true。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval import mark_to_labels as tool
from eval.self_check import check_dataset

BASE = "十年春，齐师代我。公将战，曹刿请见。肉食者谋之，又何间焉。"
# 索引对照：0十 1年 2春 3， 4齐 5师 6代 7我 8。 9公 10将 11战 12， 13曹 14刿 15请 16见 17。
#          18肉 19食 20者 21谋 22之 23， 24又 25何 26间 27焉 28。


def _write(tmp_path: Path, text: str, name: str = "case-001.marked.txt") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ 解析与索引
def test_indices_are_computed_not_guessed() -> None:
    parsed = tool.parse_marked("十年春，齐师[[代|伐]]我。", case_id="case-001")

    assert parsed.source == "十年春，齐师代我。"
    assert len(parsed.points) == 1
    point = parsed.points[0]
    assert (point.start, point.end) == (6, 7)
    # 索引必须指向原文里那个字——这是全部判定的基础
    assert parsed.source[point.start : point.end] == "代"


def test_multiple_points_shift_correctly() -> None:
    """前面的标记被去掉后，后面的索引要跟着前移——手算最常错在这里。"""
    parsed = tool.parse_marked("齐师[[代|伐]]我。[[肉食者谋之|肉食者鄙]]，又何间焉。", case_id="case-001")

    assert parsed.source == "齐师代我。肉食者谋之，又何间焉。"
    for point in parsed.points:
        assert parsed.source[point.start : point.end] == point.original
    # 0齐 1师 2代 3我 4。 5肉 6食 7者 8谋 9之
    assert [(p.start, p.end) for p in parsed.points] == [(2, 3), (5, 10)]


def test_markup_never_leaks_into_source() -> None:
    parsed = tool.parse_marked(BASE.replace("代", "[[代|伐|讹字]]"), case_id="case-001")
    assert "[[" not in parsed.source and "]]" not in parsed.source
    assert parsed.source == BASE


def test_full_markup_with_type_source_and_note() -> None:
    parsed = tool.parse_marked(
        "其名[[鲲|为鲲|脱文|injected|对文作「其名为鹏」]]。", case_id="case-001"
    )
    point = parsed.points[0]
    assert (point.type, point.source, point.note) == ("脱文", "injected", "对文作「其名为鹏」")
    assert point.inferred_edition_evidence is True


def test_type_omitted_stays_pending_instead_of_guessing() -> None:
    """不猜类型：猜错会污染逐类指标，而自检查不出来。"""
    parsed = tool.parse_marked("齐师[[代|伐]]我。", case_id="case-001")
    assert parsed.points[0].type == tool.PENDING_TYPE

    entry = tool.build_case("齐师[[代|伐]]我。", case_id="case-001")
    problems = check_dataset([entry["case"]], entry["labels"])
    assert any("不在五类内" in problem.message for problem in problems)


def test_source_defaults_to_injected() -> None:
    parsed = tool.parse_marked("齐师[[代|伐|讹字]]我。", case_id="case-001")
    assert parsed.points[0].source == "injected"


# ------------------------------------------------------------------ 诚实性默认值
def test_yiwen_without_note_is_marked_as_no_edition_evidence() -> None:
    """异文没写别本依据 → 不能凭版本判定 → false（按存疑处理，不算误报也算不上检出）。"""
    parsed = tool.parse_marked("[[肉食者谋之|肉食者鄙|异文|inherent]]", case_id="case-001")
    assert parsed.points[0].inferred_edition_evidence is False


def test_yiwen_with_note_has_edition_evidence() -> None:
    parsed = tool.parse_marked(
        "[[肉食者谋之|肉食者鄙|异文|inherent|据《左传》别本]]", case_id="case-001"
    )
    assert parsed.points[0].inferred_edition_evidence is True


def test_non_yiwen_types_keep_edition_evidence_true() -> None:
    for kind in ("讹字", "衍文", "脱文", "通假"):
        parsed = tool.parse_marked(f"齐师[[代|伐|{kind}]]我。", case_id="case-001")
        assert parsed.points[0].inferred_edition_evidence is True


# ------------------------------------------------------------------ 元信息与错误
def test_front_matter_gives_case_id_and_origin() -> None:
    parsed = tool.parse_marked(
        "# caseId: case-007\n# origin: 《庄子·逍遥游》（郭庆藩集释本）\n北冥有鱼。",
        case_id="ignored",
    )
    assert parsed.case_id == "case-007"
    assert parsed.origin == "《庄子·逍遥游》（郭庆藩集释本）"
    assert parsed.source == "北冥有鱼。"  # 元信息不进正文


def test_case_id_inferred_from_filename(tmp_path: Path) -> None:
    assert tool.infer_case_id(Path("docs/eval/annotate/case-003.marked.txt")) == "case-003"
    assert tool.infer_case_id(Path("case-003.txt")) == "case-003"


def test_meta_like_line_inside_body_is_kept_as_text() -> None:
    """正文里出现 `#` 开头的行不能再被当元信息吞掉（只在正文之前解析元信息）。"""
    parsed = tool.parse_marked("北冥有鱼。\n# 这是正文里的注释行\n化而为鸟。", case_id="case-001")
    assert "# 这是正文里的注释行" in parsed.source


@pytest.mark.parametrize(
    ("markup", "keyword"),
    [
        ("[[代]]", "应为 2–5 段"),
        ("[[代|伐|讹字|injected|注|多]]", "应为 2–5 段"),
        ("[[|伐]]", "原文段为空"),
        ("[[代|]]", "权威写法段为空"),
        ("[[代|伐|错别字]]", "不在五类内"),
        ("[[代|伐|讹字|manual]]", "必须是"),
    ],
)
def test_bad_markup_is_rejected(markup: str, keyword: str) -> None:
    with pytest.raises(tool.MarkupError) as error:
        tool.parse_marked(f"齐师{markup}我。", case_id="case-001")
    assert keyword in str(error.value)


def test_empty_body_is_rejected() -> None:
    with pytest.raises(tool.MarkupError, match="空的"):
        tool.parse_marked("# caseId: case-001\n\n", case_id="case-001")


# ------------------------------------------------------------------ 写盘合并
def test_write_merges_and_replaces_same_case(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "cases.json").write_text(
        json.dumps(
            [
                {"id": "case-001", "source": "旧文本", "origin": ""},
                {"id": "case-002", "source": "别段的文本", "origin": "《庄子》"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (dataset / "labels.json").write_text(
        json.dumps(
            [
                {"id": "case-001-point-1", "caseId": "case-001", "start": 0, "end": 1, "original": "旧",
                 "expectedSuggestion": "新", "type": "讹字", "hasEditionEvidence": True, "source": "injected"},
                {"id": "case-002-point-1", "caseId": "case-002", "start": 0, "end": 1, "original": "他",
                 "expectedSuggestion": "它", "type": "讹字", "hasEditionEvidence": True, "source": "injected"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    entry = tool.build_case("齐师[[代|伐|讹字]]我。", case_id="case-001")
    cases_count, labels_count = tool.merge_into_dataset(dataset, [entry])

    cases = json.loads((dataset / "cases.json").read_text(encoding="utf-8"))
    labels = json.loads((dataset / "labels.json").read_text(encoding="utf-8"))
    assert (cases_count, labels_count) == (2, 2)  # case-001 被覆盖，case-002 保留
    assert [case["id"] for case in cases] == ["case-001", "case-002"]
    assert cases[0]["source"] == "齐师代我。"  # 旧文本被覆盖
    # case-002 的标注必须原样保留（不能牵连别的段）
    assert {label["id"] for label in labels} == {"case-001-point-1", "case-002-point-1"}
    assert labels[0]["expectedSuggestion"] == "伐"


def test_write_rejects_duplicate_case_ids_in_one_batch(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    entry = tool.build_case("齐师[[代|伐|讹字]]我。", case_id="case-001")
    with pytest.raises(tool.MarkupError, match="重复的 caseId"):
        tool.merge_into_dataset(dataset, [entry, json.loads(json.dumps(entry))])


def test_cli_prints_indices_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "# origin: 《左传》\n十年春，齐师[[代|伐|讹字]]我。")
    assert tool.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "[6,7)" in out
    assert "代 → 伐" in out
    assert "《左传》" in out
    assert not (tmp_path / "dataset").exists()


def test_cli_warns_about_line_breaks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """换行也是字符、会占一个下标：索引不会错，但字数会高估，所以提示合成一行。"""
    path = _write(tmp_path, "# origin: 《庄子》\n北冥有鱼。\n其名为鲲。")
    assert tool.main([str(path)]) == 0
    assert "含 1 处换行" in capsys.readouterr().out


def test_cli_json_then_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "# origin: 《左传》\n十年春，齐师[[代|伐|讹字]]我。")
    dataset = tmp_path / "dataset"

    assert tool.main([str(path), "--json"]) == 0
    entries = json.loads(capsys.readouterr().out)
    assert entries[0]["case"]["id"] == "case-001"

    assert tool.main([str(path), "--dataset", str(dataset), "--write"]) == 0
    written = json.loads((dataset / "cases.json").read_text(encoding="utf-8"))
    assert written[0]["source"] == "十年春，齐师代我。"


def test_cli_rejects_origin_flag_with_multiple_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = _write(tmp_path, "齐师[[代|伐|讹字]]我。", "case-001.marked.txt")
    second = _write(tmp_path, "北冥[[有|无|讹字]]鱼。", "case-002.marked.txt")
    code = tool.main([str(first), str(second), "--origin", "《左传》"])
    assert code == 1
    assert "不要用命令行参数" in capsys.readouterr().err


# ------------------------------------------------------------------ 与自检联动
def test_generated_entries_satisfy_self_check_shape() -> None:
    """本工具生成的条目必须能被自检直接吃下（格式对得上），且区间无错。"""
    raw = "# caseId: case-001\n# origin: 《左传·庄公十年》\n" + BASE.replace(
        "齐师代我", "齐师[[代|伐|讹字|injected|形近而讹]]我"
    ).replace("肉食者谋之", "[[肉食者谋之|肉食者鄙|异文|inherent|据别本]]")
    entry = tool.build_case(raw, case_id="unused")

    problems = check_dataset([entry["case"]], entry["labels"])
    # 只剩配额与选段长度两类问题（本测试只关心"格式与区间"）
    leftover = [
        problem
        for problem in problems
        if problem.level == "error" and problem.where != "配额" and "超出" not in problem.message
    ]
    assert leftover == []


def test_generated_source_is_what_cases_json_will_contain(tmp_path: Path) -> None:
    """source 与索引必须出自同一次解析——这是本工具存在的全部理由。"""
    marked = "# caseId: case-009\n" + BASE.replace("代", "[[代|伐|讹字]]")
    entry = tool.build_case(marked, case_id="unused")
    source = entry["case"]["source"]

    assert source == BASE
    for label in entry["labels"]:
        assert source[label["start"] : label["end"]] == label["original"]
