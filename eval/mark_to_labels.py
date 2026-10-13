"""标记文本 → 标注 JSON（标注工序的第一步，把最容易错的一步交给机器）。

**为什么需要它**：标注里错得最多的不是判断，是**字符索引**。手数索引几乎必错，
而错一位不会报错、只会让整份评测的数字失真。所以工序反过来走——
人只负责"在哪里、原文是什么、权威写法是什么"，索引由脚本算。

标记语法（写在**标记文件**里，不写进最终 `source`）：

    十年春，齐师[[代|伐|讹字]]我。……其名[[鲲|为鲲|脱文]]。……[[蚤|早|通假|inherent]]起。
                                          ……[[肉食者谋之|肉食者鄙|异文|inherent|据《左传》别本]]

`[[原文|权威写法|类型|来源|备注]]`，后三段可省：
  * 只给 `[[原|改]]` 时类型留作「待定」——**不猜类型**，自检会报出来让你补；
  * 省 `来源` 默认 `injected`（人工注入，占多数）；
  * `异文` 省备注 → `hasEditionEvidence` 自动为 **false**（没写别本依据，就等于没有依据，
    这样"不确定"的默认值是诚实的那个，而不是乐观的那个）；
  * 备注里写不下 `|`（它是分隔符）。

标记文件顶部可写元信息（`#` 开头，只在正文之前生效）：
    # caseId: case-001
    # origin: 《左传·庄公十年》（杨伯峻注本）
`caseId` 也可以从文件名推断（`case-001.marked.txt` → `case-001`）。

用法：
    # 先看看算出来的区间对不对（人眼核对用，不改任何文件）
    python -m eval.mark_to_labels docs/eval/annotate/case-001.marked.txt

    # 直接写进数据集（同 caseId 覆盖，其余保留；可一次给多个文件）
    python -m eval.mark_to_labels docs/eval/annotate/*.marked.txt --write

    # 只要 JSON（自己拼装时用）
    python -m eval.mark_to_labels case-001.marked.txt --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .self_check import COLLATION_TYPES, VALID_SOURCES

DEFAULT_DATASET = Path("eval/dataset")
MARKUP = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)
META_LINE = re.compile(r"^#\s*([A-Za-z]+)\s*[:：]\s*(.+)$")
#: 类型没写时的占位符。刻意不猜——猜错类型会污染逐类指标，且自检查不出来。
PENDING_TYPE = "待定"


class MarkupError(ValueError):
    """标记文件本身写错了（不是标注判断错，是格式错）。"""


@dataclass(frozen=True)
class MarkedPoint:
    """一个标记点解析后的结果。"""

    start: int
    end: int
    original: str
    suggested: str
    type: str
    source: str
    note: str

    @property
    def inferred_edition_evidence(self) -> bool:
        """异文没写备注 = 没给别本依据 = 不能凭版本判定（EVAL §2.3）。

        其余各类的判定依据在文本内部（形近、误重、脱字），与"有没有别本"无关，故为 True。
        """
        if self.type == "异文":
            return bool(self.note.strip())
        return True


@dataclass(frozen=True)
class ParsedMark:
    """一个标记文件的解析结果。"""

    case_id: str
    origin: str
    source: str
    points: list[MarkedPoint]


def parse_marked(raw: str, *, case_id: str) -> ParsedMark:
    """解析标记文本。

    `source` 就是喂给 `cases.json` 的原文——**索引是针对它算的**，
    所以它必须与最终 `cases.json` 里的字符串逐字一致（本模块保证这点，不靠人抄）。
    """
    meta: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False
    for line in raw.splitlines():
        match = META_LINE.match(line.strip()) if not in_body else None
        if match:
            meta[match.group(1)] = match.group(2).strip()
            continue
        if line.strip():
            in_body = True
        body_lines.append(line)
    body = "\n".join(body_lines).strip("\n")

    if not body:
        raise MarkupError("标记文件是空的（正文不能为空）")

    source = ""
    points: list[MarkedPoint] = []
    cursor = 0
    for match in MARKUP.finditer(body):
        parts = match.group(1).split("|")
        if not 2 <= len(parts) <= 5:
            raise MarkupError(
                f"标记「[[{match.group(1)}]]」有 {len(parts)} 段，应为 2–5 段"
                "（原文|权威写法|类型|来源|备注）"
            )
        original, suggested = parts[0], parts[1]
        if not original:
            raise MarkupError(f"标记「[[{match.group(1)}]]」的原文段为空")
        if not suggested:
            raise MarkupError(f"标记「[[{match.group(1)}]]」的权威写法段为空")
        kind = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else PENDING_TYPE
        src = parts[3].strip() if len(parts) >= 4 and parts[3].strip() else "injected"
        note = parts[4].strip() if len(parts) >= 5 else ""

        if kind != PENDING_TYPE and kind not in COLLATION_TYPES:
            raise MarkupError(f"类型「{kind}」不在五类内：{'、'.join(COLLATION_TYPES)}")
        if src not in VALID_SOURCES:
            raise MarkupError(f"来源「{src}」必须是 {VALID_SOURCES} 之一")

        source += body[cursor : match.start()]
        start = len(source)
        source += original
        points.append(
            MarkedPoint(
                start=start,
                end=len(source),
                original=original,
                suggested=suggested,
                type=kind,
                source=src,
                note=note,
            )
        )
        cursor = match.end()
    source += body[cursor:]

    return ParsedMark(
        case_id=meta.get("caseId", case_id),
        origin=meta.get("origin", ""),
        source=source,
        points=points,
    )


def build_case(raw: str, *, case_id: str, origin: str = "") -> dict:
    """解析一个标记文件 → `{"case": {...}, "labels": [...]}`（尚未写盘）。"""
    parsed = parse_marked(raw, case_id=case_id)
    labels = [
        {
            "id": f"{parsed.case_id}-point-{index}",
            "caseId": parsed.case_id,
            "start": point.start,
            "end": point.end,
            "original": point.original,
            "expectedSuggestion": point.suggested,
            "type": point.type,
            "path": [],
            "hasEditionEvidence": point.inferred_edition_evidence,
            "source": point.source,
            "note": point.note,
        }
        for index, point in enumerate(parsed.points, start=1)
    ]
    return {
        "case": {"id": parsed.case_id, "source": parsed.source, "origin": origin or parsed.origin},
        "labels": labels,
    }


def infer_case_id(path: Path) -> str:
    """`case-001.marked.txt` → `case-001`；`case-001.txt` → `case-001`。"""
    name = path.name
    for suffix in (".marked.txt", ".mark.txt", ".txt"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def merge_into_dataset(dataset_dir: Path, entries: list[dict]) -> tuple[int, int]:
    """把条目并入 `cases.json` / `labels.json`：同 caseId 覆盖，其余保留。

    返回 (语料段数, 标注点数)。写盘前先说清覆盖了哪些——覆盖是静默数据损失的主要来源。
    """
    cases_path = dataset_dir / "cases.json"
    labels_path = dataset_dir / "labels.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8")) if cases_path.is_file() else []
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.is_file() else []

    incoming_ids = [entry["case"]["id"] for entry in entries]
    duplicates = {cid for cid in incoming_ids if incoming_ids.count(cid) > 1}
    if duplicates:
        raise MarkupError(f"同一批里出现了重复的 caseId：{'、'.join(sorted(duplicates))}")

    for entry in entries:
        case_id = entry["case"]["id"]
        cases = [case for case in cases if case.get("id") != case_id] + [entry["case"]]
        labels = [label for label in labels if label.get("caseId") != case_id] + entry["labels"]

    cases.sort(key=lambda case: str(case.get("id", "")))
    labels.sort(key=lambda label: (str(label.get("caseId", "")), label.get("start", 0)))
    dataset_dir.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    labels_path.write_text(json.dumps(labels, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(cases), len(labels)


def _describe(entry: dict) -> str:
    case = entry["case"]
    source = case["source"]
    lines = [
        f"段 {case['id']}：{len(source)} 字"
        + ("" if 200 <= len(source) <= 500 else "  ← 注意：EVAL §2.1 要求 200–500 字"),
        f"出处：{case['origin'] or '（未填 origin，报告附录要用）'}",
    ]
    if "\n" in source:
        # 换行也是字符，会占掉一个下标。索引不会因此算错（两侧同源），
        # 但字数会被高估、选段也不再是一整行——所以提醒改成整一行再标。
        lines.append(f"  ← 正文含 {source.count(chr(10))} 处换行：换行按 1 个字计入，建议合成一整行再标")
    lines.append("")
    for label in entry["labels"]:
        point_range = f"[{label['start']},{label['end']})"
        flag = "" if label["type"] != PENDING_TYPE else "  ← 类型待补"
        if label["type"] == "异文" and not label["hasEditionEvidence"]:
            flag = "  ← 异文未写别本依据，hasEditionEvidence=false（按存疑处理）"
        lines.append(
            f"  {label['id']}  {point_range}  {label['original']} → {label['expectedSuggestion']}"
            f"  [{label['type']}/{label['source']}]{flag}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="标记文本 → 标注 JSON（索引由脚本算，不手数）")
    parser.add_argument("files", nargs="+", type=Path, help="标记文件（可多个，支持通配）")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="数据集目录")
    parser.add_argument("--write", action="store_true", help="写进数据集（同 caseId 覆盖）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--origin", default="", help="出处（单文件时可用；多文件请写文件头的 # origin:）")
    parser.add_argument("--case-id", dest="case_id", default="", help="段 id（单文件时可用）")
    args = parser.parse_args(argv)

    if (args.origin or args.case_id) and len(args.files) > 1:
        print("多文件时请把 caseId / origin 写在各自文件头，不要用命令行参数（否则会串到所有段）", file=sys.stderr)
        return 1

    entries: list[dict] = []
    try:
        for path in args.files:
            if not path.is_file():
                print(f"找不到 {path}", file=sys.stderr)
                return 1
            entry = build_case(
                path.read_text(encoding="utf-8"),
                case_id=args.case_id or infer_case_id(path),
                origin=args.origin,
            )
            entries.append(entry)
    except MarkupError as error:
        print(f"标记有问题：{error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(entries, ensure_ascii=False, indent=1))
    else:
        for entry in entries:
            print(_describe(entry))
            print()

    if args.write:
        cases_count, labels_count = merge_into_dataset(args.dataset, entries)
        print(f"已写入 {args.dataset}：语料 {cases_count} 段 · 标注 {labels_count} 个点")
        print("接着跑自检：python -m eval.self_check " + str(args.dataset).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
