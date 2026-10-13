"""标注自检 —— `EVAL.md §9` 检查清单前三条的可执行版本。

为什么单独一个脚本：标注是**人工活的**，而它一旦出错，后面所有指标都不可信
（区间错一位、`text[start:end] != original`、某类不足 10 个，都不会报错，只会悄悄污染结论）。
所以把"能机器判的部分"全部机器判掉，人只需要负责**选段与判断**。

用法：
    python -m eval.self_check eval/dataset/
    python -m eval.self_check eval/dataset/ --json      # 机器可读，供 CI / run_compare 调用

退出码：无 error 时 0；有 error 时 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# 与 utils/schemas.py 的 COLLATION_TYPES 同值（改这里要同步改那边）
COLLATION_TYPES = ("讹字", "衍文", "脱文", "通假", "异文")
VALID_SOURCES = ("ocr", "injected", "inherent")

# EVAL §2.1：选段 200–500 字
MIN_CASE_CHARS, MAX_CASE_CHARS = 200, 500
# EVAL §2.2：总量 ≥60、五类各 ≥10
MIN_TOTAL_POINTS = 60
MIN_PER_TYPE = 10
# EVAL §2.1：刻意避开 Prompt 的 few-shot 示例，否则污染评测
FEWSHOT_MARKERS = ("学而时习之",)


@dataclass(frozen=True)
class Problem:
    level: str  # 'error' | 'warn'
    where: str
    message: str


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def check_dataset(cases: list[dict], labels: list[dict]) -> list[Problem]:
    """返回问题列表（空即通过）。errors 与 warns 分开看。"""
    problems: list[Problem] = []
    seen_case_ids: set[str] = set()
    by_case: dict[str, dict] = {}

    # ---- 语料 ----
    for index, case in enumerate(cases):
        where = f"case[{index}]"
        case_id = case.get("id")
        if not case_id:
            problems.append(Problem("error", where, "缺 id"))
            continue
        if case_id in seen_case_ids:
            problems.append(Problem("error", f"case {case_id}", "id 重复"))
        seen_case_ids.add(case_id)
        by_case[case_id] = case

        text = case.get("source") or ""
        if not text:
            problems.append(Problem("error", f"case {case_id}", "source 为空"))
        elif not (MIN_CASE_CHARS <= len(text) <= MAX_CASE_CHARS):
            problems.append(
                Problem(
                    "error",
                    f"case {case_id}",
                    f"选段 {len(text)} 字，超出 EVAL §2.1 要求的 {MIN_CASE_CHARS}–{MAX_CASE_CHARS}",
                )
            )
        for marker in FEWSHOT_MARKERS:
            if marker in text:
                problems.append(
                    Problem(
                        "error",
                        f"case {case_id}",
                        f"含 Prompt few-shot 片段「{marker}」——EVAL §2.1 要求避开，否则污染评测",
                    )
                )
        if not case.get("origin"):
            problems.append(Problem("warn", f"case {case_id}", "缺 origin（出处），报告附录要用"))

    # ---- 标注 ----
    type_counts = dict.fromkeys(COLLATION_TYPES, 0)
    spans_by_case: dict[str, list[tuple[int, int, str]]] = {}
    seen_label_ids: set[str] = set()
    for index, label in enumerate(labels):
        where = f"label[{index}]"
        case_id = label.get("caseId")
        if case_id not in by_case:
            problems.append(Problem("error", where, f"caseId「{case_id}」在语料里不存在"))
            continue
        text = by_case[case_id]["source"]

        # id 必须存在且唯一：它本身不参与判定，但 judge 拿它当字典键
        # （结果明细、复核清单都按 pointId 对齐）。缺 id 时这里放过、judge 才崩，
        # 报错信息还与"少填了 id"毫无关系——所以必须在这里拦住。
        label_id = label.get("id")
        if not label_id:
            problems.append(Problem("error", where, "缺 id（判定与复核清单都要用它做键）"))
        elif label_id in seen_label_ids:
            problems.append(Problem("error", where, f"id 重复：{label_id}"))
        else:
            seen_label_ids.add(label_id)

        start, end = label.get("start"), label.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            problems.append(Problem("error", f"{where} {label.get('id', '')}", "start/end 必须是整数"))
            continue
        if not (0 <= start < end <= len(text)):
            problems.append(
                Problem("error", f"{where} {label.get('id', '')}", f"区间 [{start},{end}) 越界（文本 {len(text)} 字）")
            )
            continue

        original = label.get("original")
        if text[start:end] != original:
            problems.append(
                Problem(
                    "error",
                    f"{where} {label.get('id', '')}",
                    f"text[start:end]={text[start:end]!r} 与 original={original!r} 不一致（区间错位）",
                )
            )

        kind = label.get("type")
        if kind not in COLLATION_TYPES:
            problems.append(Problem("error", f"{where} {label.get('id', '')}", f"type「{kind}」不在五类内"))
        else:
            type_counts[kind] += 1

        source = label.get("source")
        if source not in VALID_SOURCES:
            problems.append(
                Problem("error", f"{where} {label.get('id', '')}", f"source「{source}」必须是 {VALID_SOURCES} 之一")
            )

        if not isinstance(label.get("hasEditionEvidence"), bool):
            problems.append(Problem("error", f"{where} {label.get('id', '')}", "hasEditionEvidence 必须是布尔值"))

        suggestion = label.get("expectedSuggestion")
        if not suggestion:
            problems.append(Problem("error", f"{where} {label.get('id', '')}", "expectedSuggestion 为空"))
        elif kind == "异文" and suggestion == original:
            problems.append(
                Problem(
                    "error",
                    f"{where} {label.get('id', '')}",
                    "异文类的 expectedSuggestion 必须填**别本写法**，不能与 original 相同（API.md §2 的同一契约）",
                )
            )
        elif suggestion == original:
            problems.append(
                Problem("warn", f"{where} {label.get('id', '')}", "expectedSuggestion 与 original 相同，确认是否漏填")
            )

        spans_by_case.setdefault(case_id, []).append((start, end, label.get("id", "")))

    # ---- 同一段内 GT 区间不得重叠（重叠会让"一个 GT 只命中一次"的口径失效）----
    for case_id, spans in spans_by_case.items():
        ordered = sorted(spans)
        for (s1, e1, id1), (s2, _e2, id2) in zip(ordered, ordered[1:]):
            if s2 < e1:
                problems.append(
                    Problem("error", f"case {case_id}", f"GT 区间重叠：{id1} 与 {id2}（EVAL §3.1 要求互斥）")
                )

    # ---- 配额 ----
    if len(labels) < MIN_TOTAL_POINTS:
        problems.append(
            Problem("error", "配额", f"错误点总量 {len(labels)} < {MIN_TOTAL_POINTS}（EVAL §2.2）")
        )
    for kind, count in type_counts.items():
        if count < MIN_PER_TYPE:
            problems.append(
                Problem("error", "配额", f"「{kind}」只有 {count} 个，EVAL §2.2 要求各 ≥{MIN_PER_TYPE}")
            )

    # ---- 自检覆盖不到的、需要人工确认的项（EVAL §9 第 4 条）----
    if labels:
        problems.append(
            Problem(
                "warn",
                "流程",
                "「第二人抽复核 ≥20%」机器验不了——请在报告里写明复核人编号与抽样比例",
            )
        )

    return problems


def _summarize(labels: list[dict]) -> dict:
    counts = dict.fromkeys(COLLATION_TYPES, 0)
    for label in labels:
        if label.get("type") in counts:
            counts[label["type"]] += 1
    return {"total": len(labels), "byType": counts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="评测标注自检（EVAL §2 / §9）")
    parser.add_argument("dataset", type=Path, nargs="?", default=Path("eval/dataset"))
    parser.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    args = parser.parse_args(argv)

    cases_path = args.dataset / "cases.json"
    labels_path = args.dataset / "labels.json"
    if not cases_path.is_file() or not labels_path.is_file():
        print(f"找不到 {cases_path} 或 {labels_path}", file=sys.stderr)
        return 1

    cases = _load(cases_path)
    labels = _load(labels_path)
    problems = check_dataset(cases, labels)
    errors = [p for p in problems if p.level == "error"]
    warns = [p for p in problems if p.level == "warn"]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "cases": len(cases),
                    "summary": _summarize(labels),
                    "errors": [vars(p) for p in errors],
                    "warnings": [vars(p) for p in warns],
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0 if not errors else 1

    print(f"语料 {len(cases)} 段 · 标注 {len(labels)} 个点 · {_summarize(labels)['byType']}")
    for problem in errors:
        print(f"  [ERROR] {problem.where}: {problem.message}")
    for problem in warns:
        print(f"  [warn ] {problem.where}: {problem.message}")
    if errors:
        print(f"\n未通过：{len(errors)} 个错误。修掉后重跑（这是评测的数字能站住的前提）。")
        return 1
    print("\n通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
