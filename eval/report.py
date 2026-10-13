"""评测报告器 —— 把 `*.judged.json` 汇总成一张能进佐证材料的表。

只做汇总与排版，**不做判定**（判定在 `judge.py`，口径在 `eval/` 里唯一一份）。
输出：Markdown（给人看 + 贴进方案）、JSON（给看板与后续脚本）、CSV（给画图工具）。

按 `EVAL.md` 必须同时给出的东西，缺一不可：
- 四项指标：P / R（检出）/ F1 / 校正准确率，外加类型准确率（观察值）；
- **双 precision**（§3.4）：含 extra-valid 与不含，两个数并排；
- **分层**（§4）：全部返回 vs 高置信 ≥0.7；
- **逐类指标**（暴露短板类别）；
- 不可复现性信息：Prompt 版本、模型、供应商、规则开关、温度、时间（§8）。

用法：
    python -m eval.report --results eval/results/ --out docs/eval/report
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _load_judged(results_dir: Path) -> list[dict]:
    judged: list[dict] = []
    for path in sorted(results_dir.glob("*.judged.json")):
        judged.append(json.loads(path.read_text(encoding="utf-8")))
    return judged


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _row(label: str, layer: str, metrics: dict) -> list[str]:
    return [
        label,
        layer,
        _fmt(metrics["precision"]),
        _fmt(metrics["precisionWithExtraValid"]),
        _fmt(metrics["recall"]),
        _fmt(metrics["f1"]),
        _fmt(metrics["suggestionAccuracy"]),
        _fmt(metrics["typeAccuracy"]),
        str(metrics["tp"]),
        str(metrics["fp"]),
        str(metrics["fn"]),
        str(metrics["uncertain"]),
        str(metrics["duplicate"]),
        str(metrics["extraValid"]),
        str(metrics["extraInvalid"]),
    ]


HEADER = [
    "对象",
    "层",
    "P",
    "P(含extra-valid)",
    "R(检出)",
    "F1",
    "校正准确率",
    "类型准确率",
    "TP",
    "FP",
    "FN",
    "存疑",
    "重复",
    "extra-valid",
    "extra-invalid",
]


def build_markdown(judged: list[dict]) -> str:
    lines: list[str] = ["# 评测结果汇总", ""]
    lines.append("> 本表由 `python -m eval.report` 自动生成；判定口径见 `docs/EVAL.md` §3/§4。")
    lines.append("> **不要手改这张表**——数字要能追溯到 `eval/results/*.points.csv`。")
    lines.append("")

    lines.append("## 1. 主表（四项指标 + 双 precision + 分层）")
    lines.append("")
    lines.append("| " + " | ".join(HEADER) + " |")
    lines.append("|" + "---|" * len(HEADER))
    for entry in judged:
        for layer, key in (("全部返回", "all"), ("高置信≥0.7", "highConfidence")):
            lines.append("| " + " | ".join(_row(entry["label"], layer, entry["summary"][key])) + " |")
    lines.append("")
    lines.append("**读法**：`P(含extra-valid)` 与 `P` 并排看——两者差得多，说明模型报出的合法校勘点")
    lines.append("比标注人多，这正是 `EVAL.md §3.4` 要说明的事（把真学问算成误报，等于惩罚模型更懂）。")
    lines.append("`高置信≥0.7` 那一层才是**用户实际会看到并采纳**的效果。")
    lines.append("")

    lines.append("## 2. 逐类指标（暴露短板）")
    lines.append("")
    lines.append("| 对象 | 类型 | 点数 | 检出 | 召回 | 类型准确率 |")
    lines.append("|---|---|---|---|---|---|")
    for entry in judged:
        for kind, bucket in entry["perType"].items():
            lines.append(
                f"| {entry['label']} | {kind} | {bucket['total']} | {bucket['hit']} | "
                f"{_fmt(bucket['recall'])} | {_fmt(bucket['typeAccuracy'])} |"
            )
    lines.append("")

    lines.append("## 3. 逐段明细（只在段数 ≤ 20 时列出）")
    lines.append("")
    for entry in judged:
        if len(entry["perCase"]) > 20:
            lines.append(f"- {entry['label']}：{len(entry['perCase'])} 段，明细见 `eval/results/`。")
            continue
        lines.append(f"### {entry['label']}")
        lines.append("")
        lines.append("| 段 | 全部 P/R/F1 | 高置信 R | 丢弃 |")
        lines.append("|---|---|---|---|")
        for case in entry["perCase"]:
            all_row, high_row = case["all"], case["highConfidence"]
            lines.append(
                f"| {case['caseId']} | {_fmt(all_row['precision'])} / {_fmt(all_row['recall'])} / "
                f"{_fmt(all_row['f1'])} | {_fmt(high_row['recall'])} | {case['droppedCount']} |"
            )
        lines.append("")

    lines.append("## 4. 复现信息（EVAL §8 要求）")
    lines.append("")
    lines.append("| 对象 | 模型 | 供应商 | Prompt 版本 | 规则开关 | 温度 | 完成时间 |")
    lines.append("|---|---|---|---|---|---|---|")
    for entry in judged:
        lines.append(
            f"| {entry['label']} | {entry.get('model')} | — | {entry.get('promptVersion')} | "
            f"{entry.get('rulesEnabled')} | — | {entry.get('finishedAt')} |"
        )
    lines.append("")
    lines.append("> 供应商与温度在 `/health` 里有（见 `eval/results/*.raw.json` 的 `llmProvider` / `llmTemperature`）；")
    lines.append("> 本表从 judged 文件生成，故未重复携带。")
    lines.append("")

    pending = sum(len(entry.get("unreviewed", [])) for entry in judged)
    lines.append("## 5. 待人工复核（EVAL §3.4）")
    lines.append("")
    lines.append(f"- 仍有 **{pending}** 条「GT 之外的建议」未裁决；未裁决前它们**保守计入 FP**。")
    lines.append("- 裁决清单：`eval/results/review.csv`（把 `verdict` 填成 `extra-valid` / `extra-invalid` /")
    lines.append("  `duplicate` / `out-of-scope` 后，用 `--review` 重跑判定）。")
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, judged: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for entry in judged:
            for layer, key in (("all", "all"), ("high", "highConfidence")):
                writer.writerow(_row(entry["label"], layer, entry["summary"][key]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="评测报告（EVAL §3.4/§4/§8）")
    parser.add_argument("--results", type=Path, default=Path("eval/results"))
    parser.add_argument("--out", type=Path, default=Path("docs/eval/report"))
    args = parser.parse_args(argv)

    judged = _load_judged(args.results)
    if not judged:
        print(f"{args.results} 下没有 *.judged.json：先跑 judge")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    markdown = build_markdown(judged)
    (args.out.with_suffix(".md")).write_text(markdown, encoding="utf-8")
    (args.out.with_suffix(".json")).write_text(
        json.dumps(
            [
                {
                    "label": entry["label"],
                    "model": entry.get("model"),
                    "promptVersion": entry.get("promptVersion"),
                    "rulesEnabled": entry.get("rulesEnabled"),
                    "summary": entry["summary"],
                    "perType": entry["perType"],
                }
                for entry in judged
            ],
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    write_csv(args.out.with_suffix(".csv"), judged)

    print(f"报告已写出：{args.out.with_suffix('.md')} / .json / .csv（{len(judged)} 个对象）")
    for entry in judged:
        metrics = entry["summary"]["all"]
        print(
            f"  {entry['label']}: P={metrics['precision']} P(含extra)={metrics['precisionWithExtraValid']} "
            f"R={metrics['recall']} F1={metrics['f1']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
