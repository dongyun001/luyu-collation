"""统计脚本的边界用例（阶段 4）。

数字全部可手算，断言直接写出手算结果——**不是**拿脚本输出回填期望值，
否则测试只能证明"代码没变"，证明不了"算得对"。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from eval import survey_stats, timing_stats


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


# ------------------------------------------------------------------ 问卷：正向判定边界


def test_likert_positive_threshold_excludes_three(tmp_path: Path) -> None:
    """3 分不算正向（SURVEY §5）——这是最容易写错的一处边界。"""
    path = _write_csv(
        tmp_path / "pre.csv",
        ["pid", "q1"],
        [["p1", "5"], ["p2", "4"], ["p3", "3"], ["p4", "2"], ["p5", "1"]],
    )
    _, rows = survey_stats.load_responses(path)
    summary = survey_stats.summarize(rows, likert=["q1"], nps=[], single=[], multi=[], open_cols=[])

    block = summary["likert"]["q1"]
    assert block["n"] == 5
    assert block["positive"] == 2  # 只有 5 和 4
    assert block["positiveRatio"] == pytest.approx(0.4)
    assert block["mean"] == pytest.approx(3.0)


def test_missing_likert_answer_is_dropped_not_imputed(tmp_path: Path) -> None:
    """未作答逐题剔除、不填补：该题 n 变小，且不计入正向分母。"""
    path = _write_csv(
        tmp_path / "pre.csv",
        ["pid", "q1", "q2"],
        [
            ["p1", "5", "5"],
            ["p2", "4", "4"],
            ["p3", "5", ""],   # q2 未作答
        ],
    )
    _, rows = survey_stats.load_responses(path)
    summary = survey_stats.summarize(rows, likert=["q1", "q2"], nps=[], single=[], multi=[], open_cols=[])

    assert summary["likert"]["q1"]["n"] == 3
    assert summary["likert"]["q2"]["n"] == 2  # 未被填补成 3 分或均值
    assert summary["likert"]["q1"]["positiveRatio"] == pytest.approx(1.0)
    assert summary["likert"]["q2"]["positiveRatio"] == pytest.approx(1.0)
    # 作答数不一致必须显式提示，不允许悄悄算
    assert any("有效作答数不一致" in warning for warning in summary["warnings"])


def test_valid_count_requires_all_likert_answered(tmp_path: Path) -> None:
    """有效份数 = 填齐全部量表题的份数（缺一题就不算有效）。"""
    path = _write_csv(
        tmp_path / "pre.csv",
        ["pid", "q1", "q2"],
        [["p1", "5", "5"], ["p2", "4", "4"], ["p3", "5", ""], ["p4", "", ""]],
    )
    _, rows = survey_stats.load_responses(path)
    summary = survey_stats.summarize(
        rows, likert=["q1", "q2"], nps=[], single=[], multi=[], open_cols=[], issued=10
    )

    assert summary["total"] == 4
    assert summary["valid"] == 2
    assert summary["responseRate"] == pytest.approx(0.4)
    assert any("有效份数仅 2 份" in warning for warning in summary["warnings"])


def test_nps_buckets_and_score(tmp_path: Path) -> None:
    """NPS = (推广者 − 贬损者) / n × 100；7–8 分算中立，两边都不进。"""
    path = _write_csv(
        tmp_path / "post.csv",
        ["pid", "q8"],
        [["p1", "10"], ["p2", "9"], ["p3", "8"], ["p4", "7"], ["p5", "6"], ["p6", "0"]],
    )
    _, rows = survey_stats.load_responses(path)
    summary = survey_stats.summarize(rows, likert=[], nps=["q8"], single=[], multi=[], open_cols=[])

    block = summary["nps"]["q8"]
    assert (block["promoter"], block["passive"], block["detractor"]) == (2, 2, 2)
    assert block["score"] == pytest.approx(0.0)  # (2-2)/6*100


def test_single_and_multi_options(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "post.csv",
        ["pid", "q9", "q10"],
        [
            ["p1", "很有帮助", "理校;对校"],
            ["p2", "很有帮助", "对校、本校"],
            ["p3", "一般", "对校"],
        ],
    )
    _, rows = survey_stats.load_responses(path)
    summary = survey_stats.summarize(rows, likert=[], nps=[], single=["q9"], multi=["q10"], open_cols=[])

    assert summary["single"]["q9"]["options"] == {"很有帮助": 2, "一般": 1}
    # 多选分隔符 ; 、 | ； 都要认
    assert summary["multi"]["q10"]["options"]["对校"] == 3
    assert summary["multi"]["q10"]["options"]["理校"] == 1
    assert summary["multi"]["q10"]["n"] == 3


def test_open_answers_kept_verbatim(tmp_path: Path) -> None:
    """开放题只导出原话，不做任何加工。"""
    path = _write_csv(
        tmp_path / "post.csv",
        ["pid", "q11"],
        [["p1", "希望支持竖排显示"], ["p2", ""], ["p3", "建议增加版本库"]],
    )
    _, rows = survey_stats.load_responses(path)
    summary = survey_stats.summarize(rows, likert=[], nps=[], single=[], multi=[], open_cols=["q11"])

    assert summary["open"]["q11"]["n"] == 2
    assert [text for _, text in summary["open"]["q11"]["answers"]] == ["希望支持竖排显示", "建议增加版本库"]


def test_auto_detect_columns(tmp_path: Path) -> None:
    """不传列清单时：取值全在 1–5 的数值列当量表，其余当开放题。"""
    path = _write_csv(
        tmp_path / "pre.csv",
        ["pid", "q1", "q2", "q3"],
        [["p1", "5", "4", "古文基础一般"], ["p2", "3", "4", "没有基础"], ["p3", "4", "5", "较强"]],
    )
    fields, rows = survey_stats.load_responses(path)
    likert, open_cols = survey_stats.detect_columns(fields, rows)

    assert likert == ["q1", "q2"]
    assert open_cols == ["q3"]


def test_main_rejects_unknown_column(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_csv(tmp_path / "pre.csv", ["pid", "q1"], [["p1", "5"]])
    code = survey_stats.main([str(path), "--likert", "q99"])
    assert code == 1
    assert "q99" in capsys.readouterr().out


def test_main_json_output_is_parseable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_csv(tmp_path / "pre.csv", ["pid", "q1"], [["p1", "5"], ["p2", "4"]])
    assert survey_stats.main([str(path), "--likert", "q1", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["likert"]["q1"]["positiveRatio"] == 1.0


# ------------------------------------------------------------------ 计时：均值 / 倍数 / CI


def _timing_rows(tmp_path: Path) -> Path:
    return _write_csv(
        tmp_path / "timing.csv",
        ["participant", "group", "elapsedSec", "correctionsFound", "totalPoints", "notes"],
        [
            ["P01", "manual", "600", "6", "9", ""],
            ["P02", "manual", "660", "7", "9", ""],
            ["P03", "manual", "720", "6", "9", ""],
            ["P04", "assisted", "200", "8", "9", ""],
            ["P05", "assisted", "220", "9", "9", ""],
            ["P06", "assisted", "240", "8", "9", ""],
        ],
    )


def test_means_and_speedup_are_hand_checkable(tmp_path: Path) -> None:
    rows = timing_stats.load_rows(_timing_rows(tmp_path))
    summary = timing_stats.summarize(rows)

    assert summary["manual"]["mean"] == 660.0
    assert summary["assisted"]["mean"] == 220.0
    assert summary["speedup"] == 3.0  # 660 / 220
    assert summary["manual"]["median"] == 660.0
    assert summary["participants"] == 6


def test_detection_rate(tmp_path: Path) -> None:
    rows = timing_stats.load_rows(_timing_rows(tmp_path))
    summary = timing_stats.summarize(rows)

    manual = summary["detection"]["manual"]
    assert (manual["found"], manual["total"]) == (19, 27)
    assert manual["rate"] == pytest.approx(0.7037, abs=1e-4)
    assert summary["detection"]["assisted"]["rate"] == pytest.approx(25 / 27, abs=1e-4)


def test_bootstrap_ci_covers_mean_at_n3(tmp_path: Path) -> None:
    """n=3 也必须给得出区间（SURVEY §5 明确要求），且区间要包住点估计。"""
    rows = timing_stats.load_rows(_timing_rows(tmp_path))
    summary = timing_stats.summarize(rows)

    low, high = summary["manual"]["ci"]
    assert low < high
    assert low <= summary["manual"]["mean"] <= high
    # 效率倍数的区间同理
    assert summary["speedupCI"][0] <= summary["speedup"] <= summary["speedupCI"][1]


def test_bootstrap_is_reproducible() -> None:
    """固定种子：同样的输入必须给出同样的区间，否则"可复现"是空话。"""
    values = [10.0, 12.0, 14.0, 30.0]
    assert timing_stats.bootstrap_ci(values) == timing_stats.bootstrap_ci(values)
    manual, assisted = [600.0, 660.0, 720.0], [200.0, 220.0, 240.0]
    assert timing_stats.bootstrap_ratio_ci(manual, assisted) == timing_stats.bootstrap_ratio_ci(manual, assisted)


def test_bootstrap_single_value_degrades_gracefully() -> None:
    assert timing_stats.bootstrap_ci([5.0]) == (5.0, 5.0)
    assert timing_stats.bootstrap_ci([]) == (0.0, 0.0)
    assert timing_stats.bootstrap_ratio_ci([5.0], [1.0]) == (5.0, 5.0)


def test_zero_assisted_mean_does_not_crash(tmp_path: Path) -> None:
    """辅助组全 0 秒（脏数据）不得抛 ZeroDivisionError，如实报 0 并给出倍数即可。"""
    path = _write_csv(
        tmp_path / "dirty.csv",
        ["participant", "group", "elapsedSec"],
        [["P1", "manual", "600"], ["P2", "manual", "600"], ["P3", "assisted", "0"], ["P4", "assisted", "0"]],
    )
    rows = timing_stats.load_rows(path)
    summary = timing_stats.summarize(rows)

    assert summary["speedup"] == 0.0
    assert summary["speedupCI"] == [0.0, 0.0]


def test_rows_with_bad_group_or_seconds_are_skipped(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "messy.csv",
        ["participant", "group", "elapsedSec", "correctionsFound", "totalPoints"],
        [
            ["P1", "manual", "600", "6", "9"],
            ["P2", "control", "500", "5", "9"],   # 未知分组
            ["P3", "assisted", "abc", "5", "9"],  # 时间不可解析
            ["P4", "assisted", "200", "5", "9"],
        ],
    )
    rows = timing_stats.load_rows(path)
    assert [row.participant for row in rows] == ["P1", "P4"]


def test_small_sample_warns(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "small.csv",
        ["participant", "group", "elapsedSec"],
        [["P1", "manual", "600"], ["P2", "assisted", "200"]],
    )
    summary = timing_stats.summarize(timing_stats.load_rows(path))
    assert any("要求每组 ≥3" in warning for warning in summary["warnings"])


def test_markdown_report_mentions_ci_and_target(tmp_path: Path) -> None:
    rows = timing_stats.load_rows(_timing_rows(tmp_path))
    markdown = timing_stats.to_markdown(timing_stats.summarize(rows), "timing.csv")
    assert "95% CI" in markdown
    assert "≥3 倍" in markdown
