"""问卷统计 —— 按 `docs/SURVEY.md §5` 的口径算。

口径要点（照 SURVEY §5，不自行发明）：
  * **有效份数** = 填齐全部量表题的份数；某题缺失按「未作答」**逐题剔除，不填补**；
  * **正向比例** = 该题得 4–5 分的份数 ÷ 该题有效作答份数（3 分不算正向）；
  * **NPS** = (9–10 分推广者占比 − 0–6 分贬损者占比) × 100，7–8 分为中立；
  * 必须同时报**样本量与回收率**——小样本要如实写在报告里（SURVEY §5）。
  * 开放题**导出原话**，不做情绪打分、不做主题归纳（避免把主观解读当数据）。

列名由题库实际导出决定，所以本题不猜列名，用命令行显式指定：

    python -m eval.survey_stats responses.csv --issued 30 \\
        --likert q1,q2,q3,q4,q5,q6,q7 --nps q8 --single q9 --multi q10 --open q11

  --likert  1–5 量表题（正向 = 4–5）
  --nps     0–10 推荐值（一般只有后测问卷有）
  --single  单选题 → 选项分布
  --multi   多选题 → 选项出现次数（同一格内用 ; 、| 或 、 分隔）
  --open    开放题 → 导出原话
不传任何列时：自动把「取值全在 1–5 的数值列」当量表，其余列为开放题。

用法补充：
    --json          输出 JSON（机器可读）
    --open-out P    把开放题原话写成 CSV（逐条一行，便于人工编码）
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

LIKERT_POSITIVE_MIN = 4  # 4–5 计正向（SURVEY §5）
NPS_PROMOTER_MIN = 9
NPS_DETRACTOR_MAX = 6
MULTI_SEPARATORS = (";", "|", "、", "；")


def _split_multi(value: str) -> list[str]:
    parts = [value]
    for sep in MULTI_SEPARATORS:
        expanded: list[str] = []
        for part in parts:
            expanded.extend(part.split(sep))
        parts = expanded
    return [part.strip() for part in parts if part.strip()]


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_responses(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = [name.strip() for name in (reader.fieldnames or [])]
        rows = [
            {(key or "").strip(): (value or "").strip() for key, value in row.items()}
            for row in reader
        ]
    return fields, rows


def detect_columns(fields: list[str], rows: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    """没给列清单时的兜底：全为 1–5 的数值列 → 量表；其余（除 pid 类）→ 开放题。"""
    skip = {"pid", "participant", "id", "group", "timestamp", "提交时间", "序号"}
    likert: list[str] = []
    open_cols: list[str] = []
    for name in fields:
        if name.lower() in skip:
            continue
        values = [_to_float(row.get(name)) for row in rows]
        present = [value for value in values if value is not None]
        if present and all(1 <= value <= 5 for value in present) and len(present) >= max(1, len(rows) // 2):
            likert.append(name)
        elif any(row.get(name) for row in rows):
            open_cols.append(name)
    return likert, open_cols


def _likert_block(column: str, rows: list[dict[str, str]]) -> dict:
    answered = [_to_float(row.get(column)) for row in rows]
    answered = [value for value in answered if value is not None]
    if not answered:
        return {"n": 0,
                "positive": 0, "positiveRatio": 0.0, "mean": 0.0, "median": 0.0,
                "distribution": {}}
    distribution: dict[str, int] = {}
    for value in answered:
        key = str(int(value)) if float(value).is_integer() else f"{value:g}"
        distribution[key] = distribution.get(key, 0) + 1
    positives = sum(1 for value in answered if value >= LIKERT_POSITIVE_MIN)
    return {
        "n": len(answered),
        "positive": positives,
        "positiveRatio": round(positives / len(answered), 4),
        "mean": round(statistics.fmean(answered), 2),
        "median": round(statistics.median(answered), 1),
        "distribution": dict(sorted(distribution.items())),
    }


def _nps_block(column: str, rows: list[dict[str, str]]) -> dict:
    answered = [_to_float(row.get(column)) for row in rows]
    answered = [value for value in answered if value is not None]
    if not answered:
        return {"n": 0, "promoter": 0, "detractor": 0, "passive": 0, "score": 0.0}
    promoters = sum(1 for value in answered if value >= NPS_PROMOTER_MIN)
    detractors = sum(1 for value in answered if value <= NPS_DETRACTOR_MAX)
    passive = len(answered) - promoters - detractors
    return {
        "n": len(answered),
        "promoter": promoters,
        "detractor": detractors,
        "passive": passive,
        "score": round((promoters - detractors) / len(answered) * 100, 1),
    }


def _single_block(column: str, rows: list[dict[str, str]]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(column) or ""
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return {"n": sum(counts.values()), "options": dict(sorted(counts.items(), key=lambda kv: -kv[1]))}


def _multi_block(column: str, rows: list[dict[str, str]]) -> dict:
    counts: dict[str, int] = {}
    respondents = 0
    for row in rows:
        value = row.get(column) or ""
        if not value:
            continue
        respondents += 1
        for option in _split_multi(value):
            counts[option] = counts.get(option, 0) + 1
    return {"n": respondents, "options": dict(sorted(counts.items(), key=lambda kv: -kv[1]))}


def _open_block(column: str, rows: list[dict[str, str]]) -> dict:
    answers = [(index + 1, row.get(column) or "") for index, row in enumerate(rows)]
    answers = [(index, text) for index, text in answers if text.strip()]
    return {"n": len(answers), "answers": answers}


def summarize(
    rows: list[dict[str, str]],
    *,
    likert: list[str],
    nps: list[str],
    single: list[str],
    multi: list[str],
    open_cols: list[str],
    issued: int | None = None,
) -> dict:
    # 有效份数 = 填齐全部量表题的份数（逐题缺失只影响该题，不填补）
    if likert:
        valid = [
            row for row in rows
            if all(_to_float(row.get(column)) is not None for column in likert)
        ]
    else:
        valid = list(rows)

    result: dict = {
        "total": len(rows),
        "valid": len(valid),
        "issued": issued,
        "responseRate": round(len(rows) / issued, 4) if issued else None,
        "likert": {column: _likert_block(column, rows) for column in likert},
        "nps": {column: _nps_block(column, rows) for column in nps},
        "single": {column: _single_block(column, rows) for column in single},
        "multi": {column: _multi_block(column, rows) for column in multi},
        "open": {column: _open_block(column, rows) for column in open_cols},
    }
    result["warnings"] = _warnings(result)
    return result


def _warnings(summary: dict) -> list[str]:
    warnings: list[str] = []
    valid = summary["valid"]
    if valid < 15:
        warnings.append(
            f"有效份数仅 {valid} 份（SURVEY §1 目标 ≥15）——正向比例的小数位没有意义，报告里要按整数说，并注明样本量"
        )
    if summary["responseRate"] is not None and summary["responseRate"] < 0.6:
        warnings.append(f"回收率 {summary['responseRate']:.0%} 偏低，需说明发放与回收方式")
    # 逐题有效数不一致 = 存在未作答（我们选择剔除而非填补，须显式提示）
    counts = {column: block["n"] for column, block in summary["likert"].items()}
    if counts and len(set(counts.values())) > 1:
        warnings.append(f"各量表题有效作答数不一致（{counts}），已按「未作答逐题剔除、不填补」处理")
    return warnings


def to_markdown(summary: dict, source: str) -> str:
    lines = [
        "# 问卷统计",
        "",
        f"> 数据来源：`{source}`；口径见 `docs/SURVEY.md §5`，本表由 `python -m eval.survey_stats` 生成。",
        "",
        f"回收 **{summary['total']}** 份"
        + (f"（发出 {summary['issued']} 份，回收率 **{summary['responseRate']:.0%}**）" if summary["responseRate"] is not None else "")
        + f"，其中**有效 {summary['valid']} 份**（有效 = 填齐全部量表题）。",
        "",
    ]
    if summary["likert"]:
        lines += [
            "## 量表题（正向 = 4–5 分）",
            "",
            "| 题 | 有效作答 | 正向数 | 正向比例 | 均值 | 中位数 |",
            "|---|---|---|---|---|---|",
        ]
        for column, block in summary["likert"].items():
            lines.append(
                f"| {column} | {block['n']} | {block['positive']} | {block['positiveRatio']:.0%} | "
                f"{block['mean']} | {block['median']} |"
            )
        lines.append("")
    for column, block in summary["nps"].items():
        lines += [
            f"## NPS（{column}）",
            "",
            f"推广者（9–10 分）{block['promoter']} 人、中立（7–8 分）{block['passive']} 人、"
            f"贬损者（0–6 分）{block['detractor']} 人 → **NPS = {block['score']}**。",
            "",
        ]
    for title, key in (("单选题", "single"), ("多选题", "multi")):
        for column, block in summary[key].items():
            lines += [f"## {title}（{column}，n={block['n']}）", ""]
            lines += [f"- {option}：{count} 人" for option, count in block["options"].items()]
            lines.append("")
    for column, block in summary["open"].items():
        lines += [f"## 开放题（{column}，{block['n']} 条）", ""]
        lines += [f"{index}. {text}" for index, text in block["answers"]]
        lines.append("")
    if summary["warnings"]:
        lines.append("**必须写进报告的提醒**：")
        lines.extend(f"- {warning}" for warning in summary["warnings"])
        lines.append("")
    return "\n".join(lines)


def _write_open_csv(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["column", "rowIndex", "text"])
        for column, block in summary["open"].items():
            for index, text in block["answers"]:
                writer.writerow([column, index, text])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="问卷统计（SURVEY §5）")
    parser.add_argument("csv", type=Path, help="回收答卷 CSV（UTF-8，带表头）")
    parser.add_argument("--issued", type=int, help="发出份数，用于算回收率")
    parser.add_argument("--likert", default="", help="逗号分隔的 1–5 量表列名")
    parser.add_argument("--nps", default="", help="逗号分隔的 0–10 推荐值列名")
    parser.add_argument("--single", default="", help="逗号分隔的单选列名")
    parser.add_argument("--multi", default="", help="逗号分隔的多选列名")
    parser.add_argument("--open", dest="open_cols", default="", help="逗号分隔的开放题列名")
    parser.add_argument("--out", type=Path, help="把 Markdown 写到该路径")
    parser.add_argument("--open-out", type=Path, help="把开放题原话写成 CSV")
    parser.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    args = parser.parse_args(argv)

    if not args.csv.is_file():
        print(f"找不到 {args.csv}")
        return 1
    fields, rows = load_responses(args.csv)
    if not rows:
        print("答卷为空")
        return 1

    def columns(raw: str) -> list[str]:
        return [name.strip() for name in raw.split(",") if name.strip()]

    likert, nps = columns(args.likert), columns(args.nps)
    single, multi, open_cols = columns(args.single), columns(args.multi), columns(args.open_cols)
    if not any((likert, nps, single, multi, open_cols)):
        likert, open_cols = detect_columns(fields, rows)
        print(f"[自动识别] 量表列：{likert or '无'}；开放列：{open_cols or '无'}\n")

    unknown = [
        name for name in likert + nps + single + multi + open_cols if name not in fields
    ]
    if unknown:
        print(f"这些列在 CSV 里不存在：{unknown}\n实际表头：{fields}")
        return 1

    summary = summarize(
        rows, likert=likert, nps=nps, single=single, multi=multi, open_cols=open_cols, issued=args.issued
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    else:
        markdown = to_markdown(summary, str(args.csv))
        print(markdown)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(markdown, encoding="utf-8")
            print(f"\n已写出：{args.out}")
    if args.open_out:
        _write_open_csv(args.open_out, summary)
        print(f"开放题原话已写出：{args.open_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
