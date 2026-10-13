"""效率实验统计 —— 按 `docs/SURVEY.md §3/§5` 的口径算，并**必须给置信区间**。

为什么坚持给区间：每组只有 3 人左右，均值极其不稳（一个人快慢就能把"提升 3 倍"推翻）。
SURVEY §5 明确写"不要只给均值"，本脚本把它变成默认行为：**Bootstrap 置信区间**，
不引 scipy，只用标准库 `random`（固定种子，结果可复现）。

命中率（`correctionsFound / totalPoints`）按 `EVAL.md §3.1` 的区间口径判出来后填进 CSV，
本脚本只做算术，不重新判定。

输入 CSV（SURVEY §3）：`participant,group,elapsedSec,correctionsFound,totalPoints,notes`
    P07,assisted,214,7,9,备注
    P08,manual,612,6,9,

用法：
    python -m eval.timing_stats docs/eval/survey/timing.csv
    python -m eval.timing_stats docs/eval/survey/timing.csv --json
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

MANUAL, ASSISTED = "manual", "assisted"
BOOTSTRAP_ROUNDS = 10_000
# 固定种子：换机器/换时间跑出来的区间必须一样，否则"复现"无从谈起
BOOTSTRAP_SEED = 20261013


@dataclass
class Row:
    participant: str
    group: str
    elapsed_sec: float
    found: int
    total: int


def load_rows(path: Path) -> list[Row]:
    rows: list[Row] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            group = (raw.get("group") or "").strip().lower()
            if group not in (MANUAL, ASSISTED):
                continue
            try:
                seconds = float(raw["elapsedSec"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append(
                Row(
                    participant=(raw.get("participant") or "").strip(),
                    group=group,
                    elapsed_sec=seconds,
                    found=int(float(raw.get("correctionsFound") or 0)),
                    total=int(float(raw.get("totalPoints") or 0)),
                )
            )
    return rows


def bootstrap_ci(values: list[float], *, rounds: int = BOOTSTRAP_ROUNDS, seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """均值的 95% 百分位 Bootstrap 区间。n<2 时无法给出区间，返回 (均值, 均值)。"""
    if len(values) < 2:
        mean = statistics.fmean(values) if values else 0.0
        return mean, mean
    rng = random.Random(seed)
    means = []
    for _ in range(rounds):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.fmean(sample))
    means.sort()
    low = means[int(0.025 * rounds)]
    high = means[min(rounds - 1, int(0.975 * rounds))]
    return low, high


def bootstrap_ratio_ci(
    manual: list[float], assisted: list[float], *, rounds: int = BOOTSTRAP_ROUNDS, seed: int = BOOTSTRAP_SEED
) -> tuple[float, float]:
    """效率倍数（人工均值 ÷ 辅助均值）的 95% 区间。

    注意它**不是**两个区间相除——那样会把误差放大得没有意义；这里对两组同时重采样再取比值。
    """
    if len(manual) < 2 or len(assisted) < 2:
        ratio = statistics.fmean(manual) / statistics.fmean(assisted) if manual and assisted else 0.0
        return ratio, ratio
    rng = random.Random(seed + 1)
    ratios = []
    for _ in range(rounds):
        m = statistics.fmean([manual[rng.randrange(len(manual))] for _ in manual])
        a = statistics.fmean([assisted[rng.randrange(len(assisted))] for _ in assisted])
        if a > 0:
            ratios.append(m / a)
    if not ratios:
        return 0.0, 0.0
    ratios.sort()
    return ratios[int(0.025 * len(ratios))], ratios[min(len(ratios) - 1, int(0.975 * len(ratios)))]


def _safe_ratio(manual: list[float], assisted: list[float]) -> float:
    """效率倍数。分母为 0（辅助组全 0 秒，只可能是脏数据）时返回 0 而不是抛异常——
    统计脚本遇到脏数据应当如实报 0 并让 warnings 去说，不能把整批数据卡死。"""
    if not manual or not assisted:
        return 0.0
    denominator = statistics.fmean(assisted)
    if denominator <= 0:
        return 0.0
    return statistics.fmean(manual) / denominator


def summarize(rows: list[Row]) -> dict:
    manual = [row.elapsed_sec for row in rows if row.group == MANUAL]
    assisted = [row.elapsed_sec for row in rows if row.group == ASSISTED]

    def block(values: list[float]) -> dict:
        if not values:
            return {"n": 0, "mean": 0.0, "median": 0.0, "ci": [0.0, 0.0]}
        low, high = bootstrap_ci(values)
        return {
            "n": len(values),
            "mean": round(statistics.fmean(values), 1),
            "median": round(statistics.median(values), 1),
            "ci": [round(low, 1), round(high, 1)],
        }

    ratio = _safe_ratio(manual, assisted)
    ratio_low, ratio_high = bootstrap_ratio_ci(manual, assisted)

    def hit_rate(group: str) -> dict:
        subset = [row for row in rows if row.group == group]
        found = sum(row.found for row in subset)
        total = sum(row.total for row in subset)
        return {"found": found, "total": total, "rate": round(found / total, 4) if total else 0.0}

    return {
        "manual": block(manual),
        "assisted": block(assisted),
        "speedup": round(ratio, 2),
        "speedupCI": [round(ratio_low, 2), round(ratio_high, 2)],
        "detection": {MANUAL: hit_rate(MANUAL), ASSISTED: hit_rate(ASSISTED)},
        "participants": len(rows),
        "warnings": _warnings(len(manual), len(assisted)),
    }


def _warnings(n_manual: int, n_assisted: int) -> list[str]:
    warnings: list[str] = []
    for label, count in (("人工组", n_manual), ("辅助组", n_assisted)):
        if count < 3:
            warnings.append(f"{label}只有 {count} 人（SURVEY §1 要求每组 ≥3）——区间会很宽，报告里要如实说明")
        elif count < 5:
            warnings.append(f"{label}仅 {count} 人，置信区间偏宽，结论表述要留余地")
    return warnings


def to_markdown(summary: dict, source: str) -> str:
    manual, assisted = summary["manual"], summary["assisted"]
    lines = [
        "# 效率实验统计",
        "",
        f"> 数据来源：`{source}`；口径见 `docs/SURVEY.md §3/§5`，本表由 `python -m eval.timing_stats` 生成。",
        "",
        "| 组 | n | 均值(秒) | 中位数(秒) | 均值 95% CI | 命中率 |",
        "|---|---|---|---|---|---|",
        f"| 人工组 | {manual['n']} | {manual['mean']} | {manual['median']} | {manual['ci'][0]}–{manual['ci'][1]} | "
        f"{summary['detection'][MANUAL]['rate']:.3f} |",
        f"| 辅助组 | {assisted['n']} | {assisted['mean']} | {assisted['median']} | {assisted['ci'][0]}–{assisted['ci'][1]} | "
        f"{summary['detection'][ASSISTED]['rate']:.3f} |",
        "",
        f"**效率倍数（人工均值 ÷ 辅助均值）= {summary['speedup']}**，95% CI **{summary['speedupCI'][0]}–{summary['speedupCI'][1]}**"
        f"（PRD §6 目标 ≥3 倍）。",
        "",
        "**读法**：区间跨过 3 就说明「提升 3 倍」在当前样本量下**还不能下定论**；",
        "样本量小（每组 3–5 人）时这是常态，报告里必须如实写出来，而不是只报那个点估计。",
        "",
    ]
    if summary["warnings"]:
        lines.append("**样本量提醒**：")
        lines.extend(f"- {warning}" for warning in summary["warnings"])
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="效率实验统计（SURVEY §3/§5）")
    parser.add_argument("csv", type=Path, help="计时 CSV")
    parser.add_argument("--out", type=Path, help="把 Markdown 写到该路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    args = parser.parse_args(argv)

    if not args.csv.is_file():
        print(f"找不到 {args.csv}")
        return 1
    rows = load_rows(args.csv)
    if not rows:
        print("没有可用行（需要 group ∈ {manual, assisted} 且 elapsedSec 可解析）")
        return 1

    summary = summarize(rows)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    else:
        markdown = to_markdown(summary, str(args.csv))
        print(markdown)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(markdown, encoding="utf-8")
            print(f"\n已写出：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
