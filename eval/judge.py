"""评测判定器 —— `EVAL.md §3` 的实现（本文件是"数字从哪来"的唯一入口）。

四条口径，逐条对应 EVAL：

1. **以位置区间为主**（§3.1）：命中条件 = 建议区间与 GT 区间有重叠，且
   `重叠长度 ≥ min(len(建议), len(GT)) × 50%`。不用字符串相等——模型常给带上下文的片段。
2. **一个 GT 只命中一次**（§3.1）：多条建议命中同一 GT 时取重叠最大者为命中，其余记 **重复**（不计 FP）。
3. **检出与分类分开**（§3.2）：区间命中即算检出；类型对不对单独算"类型准确率"。
4. **额外正确单列**（§3.4）：GT 之外的建议**必须由标注人复核**才能算 extra-valid。
   本脚本**不自动判**——它把这些建议导出成复核清单（`.review.csv`），人填 `verdict` 后再喂回来
   （`--review`）。没填的部分**保守计入 FP**，绝不自作主张算成"正确"。

另按 §3.5：GT `hasEditionEvidence=false` 的点，模型报了按**存疑**记（不计 TP 也不计 FP）。
按 §4：所有指标**分两层**报——「全部返回」与「高置信 ≥0.7」。

用法：
    python -m eval.judge --dataset eval/dataset/ --results eval/results/
    python -m eval.judge --dataset eval/dataset/ --raw eval/results/mimo.raw.json
    python -m eval.judge --dataset eval/dataset/ --results eval/results/ --review eval/results/review.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

# 与 API.md §2 / EVAL §4 同值
HIGH_CONFIDENCE = 0.7
# EVAL §3.1：重叠长度 ≥ min(len(建议), len(GT)) 的 50%
OVERLAP_RATIO = 0.5
# 复核清单里允许的判定值（EVAL §3.4）
REVIEW_VERDICTS = ("extra-valid", "extra-invalid", "duplicate", "out-of-scope")


# --------------------------------------------------------------------------- 基础工具
def item_span(item: dict) -> tuple[int, int]:
    """建议在底本里的区间（左闭右开）。"""
    start = int(item["offset"])
    return start, start + len(item["original"])


def gt_span(gt: dict) -> tuple[int, int]:
    return int(gt["start"]), int(gt["end"])


def overlap_length(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def is_hit_candidate(item: dict, gt: dict) -> bool:
    """EVAL §3.1 的命中条件。"""
    a, b = item_span(item), gt_span(gt)
    overlap = overlap_length(a, b)
    if overlap <= 0:
        return False
    smaller = min(a[1] - a[0], b[1] - b[0])
    return overlap >= smaller * OVERLAP_RATIO


@dataclass
class CaseMatch:
    """一段用例的匹配结果。"""

    case_id: str
    matches: list[tuple[dict, dict]] = field(default_factory=list)  # (建议, GT)
    unmatched_items: list[dict] = field(default_factory=list)
    unmatched_gts: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)


def match_case(case_id: str, items: list[dict], gts: list[dict]) -> CaseMatch:
    """贪心分配：先把重叠最大的配对钉死，保证"一个 GT 只命中一次、一个建议最多命中一个 GT"。"""
    candidates: list[tuple[int, int, int]] = []  # (重叠长度, item 下标, gt 下标)
    for i, item in enumerate(items):
        for j, gt in enumerate(gts):
            if is_hit_candidate(item, gt):
                candidates.append((overlap_length(item_span(item), gt_span(gt)), i, j))
    # 重叠大的优先；并列时按下标稳定排序，保证同输入同输出
    candidates.sort(key=lambda triple: (-triple[0], triple[1], triple[2]))

    used_items: set[int] = set()
    used_gts: set[int] = set()
    result = CaseMatch(case_id=case_id)
    for _overlap, i, j in candidates:
        if i in used_items or j in used_gts:
            continue
        used_items.add(i)
        used_gts.add(j)
        result.matches.append((items[i], gts[j]))

    for i, item in enumerate(items):
        if i in used_items:
            continue
        # 与**某个已命中的 GT** 有任一部分重叠 → 判为重复（EVAL §3.1），不算 FP
        if any(overlap_length(item_span(item), gt_span(gts[j])) > 0 for j in used_gts):
            result.duplicates.append(item)
        else:
            result.unmatched_items.append(item)
    result.unmatched_gts = [gt for j, gt in enumerate(gts) if j not in used_gts]
    return result


# --------------------------------------------------------------------------- 指标
def _metrics(rows: dict[str, int]) -> dict[str, float]:
    tp, fp, fn = rows["tp"], rows["fp"], rows["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    matched = rows["matched"]
    return {
        **rows,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "suggestionAccuracy": round(rows["suggestionCorrect"] / matched, 4) if matched else 0.0,
        "typeAccuracy": round(rows["typeCorrect"] / matched, 4) if matched else 0.0,
    }


def _blank_rows() -> dict[str, int]:
    return {
        "matched": 0,
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "typeCorrect": 0,
        "suggestionCorrect": 0,
        "uncertain": 0,
        "duplicate": 0,
        "extraValid": 0,
        "extraInvalid": 0,
        "outOfScope": 0,
    }


def judge_case(case_match: CaseMatch, review: dict[str, str] | None = None) -> dict:
    """把一段的匹配结果折算成指标（**不含** extra-valid 的口径修正，那一步在 judge_dataset）。"""
    rows = _blank_rows()
    detail: list[dict] = []
    for item, gt in case_match.matches:
        rows["matched"] += 1
        if item.get("type") == gt.get("type"):
            rows["typeCorrect"] += 1
        suggestion_ok = item.get("suggested") == gt.get("expectedSuggestion")
        if suggestion_ok:
            rows["suggestionCorrect"] += 1
        # EVAL §3.5：无版本依据的 GT，模型报了按存疑记（不计 TP 也不计 FP）
        if gt.get("hasEditionEvidence") is False:
            rows["uncertain"] += 1
        else:
            rows["tp"] += 1
        detail.append(
            {
                "pointId": gt.get("id"),
                "itemId": item.get("id"),
                "hit": True,
                "typeCorrect": item.get("type") == gt.get("type"),
                "suggestionCorrect": suggestion_ok,
                "uncertain": gt.get("hasEditionEvidence") is False,
                "confidence": item.get("confidence"),
                "suggested": item.get("suggested"),
                "expectedSuggestion": gt.get("expectedSuggestion"),
            }
        )

    for gt in case_match.unmatched_gts:
        if gt.get("hasEditionEvidence") is False:
            rows["uncertain"] += 1  # 存疑点没被报，也不算漏检
        else:
            rows["fn"] += 1
        detail.append({"pointId": gt.get("id"), "hit": False, "typeCorrect": False, "suggestionCorrect": False})

    rows["duplicate"] += len(case_match.duplicates)
    # 未匹配的建议：没复核就保守算 FP；复核后按裁决归位（§3.4）
    for item in case_match.unmatched_items:
        verdict = (review or {}).get(str(item.get("id")))
        if verdict == "extra-valid":
            rows["extraValid"] += 1
        elif verdict == "out-of-scope":
            rows["outOfScope"] += 1
        elif verdict == "duplicate":
            rows["duplicate"] += 1
        elif verdict == "extra-invalid":
            rows["extraInvalid"] += 1
            rows["fp"] += 1
        else:
            rows["fp"] += 1  # 未复核 → 保守
        detail.append(
            {
                "itemId": item.get("id"),
                "hit": False,
                "verdict": verdict or "unreviewed",
                "confidence": item.get("confidence"),
                "original": item.get("original"),
                "suggested": item.get("suggested"),
            }
        )
    return {"rows": rows, "detail": detail}


# --------------------------------------------------------------------------- 顶层
def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_review(path: Path | None) -> dict[str, str]:
    """复核清单：`kind,refId,verdict,note`；只认 `verdict` 在 REVIEW_VERDICTS 内的行。"""
    if path is None or not path.is_file():
        return {}
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            verdict = (row.get("verdict") or "").strip()
            ref = (row.get("refId") or "").strip()
            if ref and verdict in REVIEW_VERDICTS:
                mapping[ref] = verdict
    return mapping


def judge_dataset(dataset_dir: Path, raw: dict, review: dict[str, str] | None = None) -> dict:
    """raw 的形状见 run_compare.py：{label, model, promptVersion, rulesEnabled, cases:[{caseId, items, droppedCount}]}"""
    cases = {case["id"]: case for case in _load_json(dataset_dir / "cases.json")}
    labels: list[dict] = _load_json(dataset_dir / "labels.json")
    by_case: dict[str, list[dict]] = {}
    for label in labels:
        by_case.setdefault(label["caseId"], []).append(label)

    all_rows, high_rows = _blank_rows(), _blank_rows()
    per_case: list[dict] = []
    per_type: dict[str, dict[str, int]] = {}
    unreviewed: list[dict] = []

    for entry in raw.get("cases", []):
        case_id = entry["caseId"]
        items = entry.get("items", [])
        gts = by_case.get(case_id, [])
        if not gts:
            continue
        case_match = match_case(case_id, items, gts)
        judged = judge_case(case_match, review)

        # 分层：高置信只留 confidence ≥ 0.7 的建议（GT 不变，故漏检会变多——这正是要看的）
        high_items = [i for i in items if float(i.get("confidence", 0)) >= HIGH_CONFIDENCE]
        high_match = match_case(case_id, high_items, gts)
        high_judged = judge_case(high_match, review)

        for key, value in judged["rows"].items():
            all_rows[key] += value
        for key, value in high_judged["rows"].items():
            high_rows[key] += value

        for gt in gts:
            bucket = per_type.setdefault(gt["type"], {"total": 0, "hit": 0, "typeCorrect": 0})
            bucket["total"] += 1
            if any(gt is matched_gt for _item, matched_gt in case_match.matches):
                bucket["hit"] += 1
        for item, gt in case_match.matches:
            if item.get("type") == gt.get("type"):
                per_type[gt["type"]]["typeCorrect"] += 1

        for item in case_match.unmatched_items:
            if str(item.get("id")) not in (review or {}):
                unreviewed.append(
                    {
                        "caseId": case_id,
                        "kind": "unmatched-item",
                        "refId": item.get("id"),
                        "original": item.get("original"),
                        "suggested": item.get("suggested"),
                        "reason": item.get("reason"),
                        "confidence": item.get("confidence"),
                        "verdict": "",
                        "note": "",
                    }
                )

        per_case.append(
            {
                "caseId": case_id,
                "droppedCount": entry.get("droppedCount", 0),
                "all": _metrics(judged["rows"]),
                "highConfidence": _metrics(high_judged["rows"]),
                # 逐点明细留给 write_points_csv 填 EVAL §5 的 hit/typeCorrect/suggestionCorrect
                "detail": judged["detail"],
            }
        )

    all_metrics = _metrics(all_rows)
    high_metrics = _metrics(high_rows)
    # EVAL §3.4 要求同时给「含 extra-valid 的 P」与「不含的 P」
    for metrics, rows in ((all_metrics, all_rows), (high_metrics, high_rows)):
        tp, fp, extra = rows["tp"], rows["fp"], rows["extraValid"]
        metrics["precisionWithExtraValid"] = round(tp / (tp + fp + extra), 4) if (tp + fp + extra) else 0.0

    return {
        "label": raw.get("label"),
        "model": raw.get("model"),
        "promptVersion": raw.get("promptVersion"),
        "rulesEnabled": raw.get("rulesEnabled"),
        "finishedAt": raw.get("finishedAt"),
        "summary": {"all": all_metrics, "highConfidence": high_metrics},
        "perCase": per_case,
        "perType": {
            kind: {
                **bucket,
                "recall": round(bucket["hit"] / bucket["total"], 4) if bucket["total"] else 0.0,
                "typeAccuracy": round(bucket["typeCorrect"] / bucket["hit"], 4) if bucket["hit"] else 0.0,
            }
            for kind, bucket in sorted(per_type.items())
        },
        "unreviewed": unreviewed,
    }


CSV_COLUMNS = (
    "model",
    "promptVersion",
    "rulesEnabled",
    "caseId",
    "pointId",
    "hit",
    "typeCorrect",
    "suggestionCorrect",
    "extraValid",
    "extraInvalid",
    "confidence",
    "dropped",
)


def write_points_csv(path: Path, judged: dict, dataset_dir: Path) -> None:
    """逐点结果，列严格照 EVAL §5（多出 `rulesEnabled` 一列，见 EVAL §8.2 的自动记录）。

    - **每个 GT 点一行**：`hit` 是区间命中（§3.2 的检出），`typeCorrect`/`suggestionCorrect` 分开记；
    - **每条复核为 extra-valid / extra-invalid 的建议也各一行**（`pointId` 前缀 `extra:`），
      因为它们既不是 GT 也不是普通误报——EVAL §3.4 要求单列；
    - 未复核的建议以 `unreviewed:<id>` 记一行（`hit=0`，并在报告里单列条数），**不伪装成已裁决**。
    """
    labels: list[dict] = _load_json(dataset_dir / "labels.json")
    by_case: dict[str, list[dict]] = {}
    for label in labels:
        by_case.setdefault(label["caseId"], []).append(label)

    rows: list[dict] = []

    def base_row(case_id: str, point_id: str, dropped) -> dict:
        return {
            "model": judged["model"],
            "promptVersion": judged["promptVersion"],
            "rulesEnabled": judged["rulesEnabled"],
            "caseId": case_id,
            "pointId": point_id,
            "hit": "",
            "typeCorrect": "",
            "suggestionCorrect": "",
            "extraValid": "",
            "extraInvalid": "",
            "confidence": "",
            "dropped": dropped,
        }

    for case in judged["perCase"]:
        case_id = case["caseId"]
        dropped = case["droppedCount"]
        detail = {d.get("pointId"): d for d in case.get("detail", []) if d.get("pointId")}

        for gt in by_case.get(case_id, []):
            entry = detail.get(gt["id"], {})
            row = base_row(case_id, gt["id"], dropped)
            row["hit"] = int(bool(entry.get("hit")))
            row["typeCorrect"] = "" if not entry.get("hit") else int(bool(entry.get("typeCorrect")))
            row["suggestionCorrect"] = "" if not entry.get("hit") else int(bool(entry.get("suggestionCorrect")))
            row["confidence"] = entry.get("confidence", "")
            rows.append(row)

        for entry in case.get("detail", []):
            verdict = entry.get("verdict")
            if verdict not in ("extra-valid", "extra-invalid"):
                continue
            row = base_row(case_id, f"extra:{entry.get('itemId')}", dropped)
            row["hit"] = 0
            row["extraValid"] = 1 if verdict == "extra-valid" else ""
            row["extraInvalid"] = 1 if verdict == "extra-invalid" else ""
            row["confidence"] = entry.get("confidence", "")
            rows.append(row)

    for item in judged.get("unreviewed", []):
        row = base_row(item["caseId"], f"unreviewed:{item['refId']}", "")
        row["hit"] = 0
        row["confidence"] = item.get("confidence", "")
        rows.append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_review_csv(path: Path, judged_list: list[dict]) -> None:
    """把所有"GT 之外的建议"汇总成复核清单，交给标注人填 verdict（EVAL §3.4 的人工那一步）。"""
    rows: list[dict] = []
    for judged in judged_list:
        rows.extend(judged.get("unreviewed", []))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("caseId", "kind", "refId", "original", "suggested", "reason", "confidence", "verdict", "note"),
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"复核清单已写出：{path}（{len(rows)} 条待人工裁决，裁决值 ∈ {REVIEW_VERDICTS}）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="评测判定（EVAL §3/§4）")
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset"))
    parser.add_argument("--results", type=Path, help="批量：目录下的 *.raw.json")
    parser.add_argument("--raw", type=Path, help="单个 raw.json")
    parser.add_argument("--review", type=Path, help="复核清单 CSV（可选）")
    parser.add_argument("--out", type=Path, default=Path("eval/results"))
    args = parser.parse_args(argv)

    raw_paths: list[Path] = []
    if args.raw:
        raw_paths.append(args.raw)
    if args.results:
        raw_paths.extend(sorted(args.results.glob("*.raw.json")))
    if not raw_paths:
        print("没有可判定的 raw.json：请给 --raw 或 --results")
        return 1

    review = load_review(args.review)
    judged_list = []
    for raw_path in raw_paths:
        judged = judge_dataset(args.dataset, _load_json(raw_path), review)
        judged_list.append(judged)
        stem = raw_path.name.removesuffix(".raw.json")
        (args.out / f"{stem}.judged.json").write_text(
            json.dumps(judged, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        write_points_csv(args.out / f"{stem}.points.csv", judged, args.dataset)
        summary = judged["summary"]
        print(
            f"{stem}: 全部返回 P={summary['all']['precision']} R={summary['all']['recall']} "
            f"F1={summary['all']['f1']} | 高置信 R={summary['highConfidence']['recall']} "
            f"| 待复核 {len(judged['unreviewed'])} 条"
        )

    write_review_csv(args.out / "review.csv", judged_list)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
