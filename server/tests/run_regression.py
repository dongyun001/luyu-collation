"""Prompt 回归集执行器 —— 把 `prompts/regression/` 的固定文本跑一遍并核对期望要点。

用途：改了 `collate_v2.md`（或 `analyze_v1.md`）之后，用同一组用例对比是否退化。
不参与生产链路；需要真实密钥（读 .env），会产生真实的模型调用费用。

按用例文件里的 `endpoint` 字段自动分流：
    POST /api/v1/collate  -> 核对 mustFind / minItems / maxItems / maxDropped
    POST /api/v1/analyze  -> 核对 minJudged / maxJudged / mustJudge / requireRelations
                             （并永远检查「无依据不得自称确定」这条不变式）

用法：
    ./.venv/Scripts/python.exe -m server.tests.run_regression
    ./.venv/Scripts/python.exe -m server.tests.run_regression --only reg-005
    ./.venv/Scripts/python.exe -m server.tests.run_regression --verbose   # 打印每条建议/每个维度
    ./.venv/Scripts/python.exe -m server.tests.run_regression --cases collation_cases_v1.json
    ./.venv/Scripts/python.exe -m server.tests.run_regression --cases analyze_cases_v1.json

退出码：全部通过 0；有失败 1。这样可以直接挂到 CI 或演示前的冒烟流程里。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import app
from server.utils.schemas import COLLATION_TYPES

CASES_DIR = Path(__file__).resolve().parent.parent / "prompts" / "regression"
# 默认跑最新的用例集；要拿旧版对比就显式 --cases collation_cases_v1.json
DEFAULT_CASES = "collation_cases_v2.json"


@dataclass
class CaseResult:
    case_id: str
    kind: str
    origin: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    item_count: int = 0
    dropped: int = 0
    types: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    error: str = ""


def _load_cases(name: str) -> tuple[dict, list[dict]]:
    path = CASES_DIR / name
    if not path.is_file():
        available = sorted(p.name for p in CASES_DIR.glob("*_cases_*.json"))
        raise SystemExit(f"用例文件不存在：{path}\n可选：{available}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, payload["cases"]


def _check_case(case: dict, body: dict) -> list[str]:
    """核对 mustFind / minItems / maxItems，返回问题列表（空即通过）。"""
    problems: list[str] = []
    items = body.get("items", [])
    expected = case.get("expected", {})

    minimum = expected.get("minItems", 0)
    maximum = expected.get("maxItems")
    if len(items) < minimum:
        problems.append(f"条数 {len(items)} < minItems {minimum}（漏报）")
    if maximum is not None and len(items) > maximum:
        problems.append(f"条数 {len(items)} > maxItems {maximum}（误报）")

    max_dropped = expected.get("maxDropped")
    if max_dropped is not None and body.get("droppedCount", 0) > max_dropped:
        problems.append(
            f"droppedCount {body['droppedCount']} > maxDropped {max_dropped}"
            "（模型仍产出不合契约的条目，说明约束没起作用）"
        )

    # 契约不变式：suggested 不得等于 original（API.md §2）。后端 schema 闸门本已丢弃这类
    # 条目，所以正常永远不触发；留着是为了万一哪天闸门被放宽时能被发现。
    degenerate = [item["original"] for item in items if item["suggested"] == item["original"]]
    if degenerate:
        problems.append(f"出现 suggested 与 original 相同的空操作条目：{degenerate}")

    for want in expected.get("mustFind", []):
        hit = any(
            item["type"] == want["type"]
            and want.get("originalContains", "") in item["original"]
            and want.get("suggestContains", "") in item["suggested"]
            for item in items
        )
        if not hit:
            problems.append(
                f"未命中必须找到的条目：type={want['type']} "
                f"original 含 {want.get('originalContains', '')!r} / "
                f"suggested 含 {want.get('suggestContains', '')!r}"
            )

    unknown = [item["type"] for item in items if item["type"] not in COLLATION_TYPES]
    if unknown:
        problems.append(f"出现五类之外的校勘类型：{unknown}")

    return problems


def _check_analyze_case(case: dict, body: dict) -> list[str]:
    """核对 minJudged / maxJudged / mustJudge / requireRelations，返回问题列表（空即通过）。

    **结构与正确性分开**（与 docs/EVAL.md §1 的「检出与分类分开算」同一思路）：
    这里只查"是否按七维输出、是否拒绝硬判"，不判"作者与年代对不对"——那部分
    有异说、需要人工核验，见 docs/EVAL.md §10。
    """
    problems: list[str] = []
    expected = case.get("expected", {})
    dimensions = body.get("dimensions", [])
    judged = [d for d in dimensions if not d.get("missing")]

    minimum = expected.get("minJudged", 0)
    if len(judged) < minimum:
        problems.append(f"作出判断的维度 {len(judged)} < minJudged {minimum}（该给判断的没给）")

    maximum = expected.get("maxJudged")
    if maximum is not None and len(judged) > maximum:
        problems.append(
            f"作出判断的维度 {len(judged)} > maxJudged {maximum}（信息不足却硬判，本 Prompt 最忌这一点）"
        )

    max_dropped = expected.get("maxDropped")
    if max_dropped is not None and body.get("droppedCount", 0) > max_dropped:
        problems.append(
            f"droppedCount {body['droppedCount']} > maxDropped {max_dropped}"
            "（模型仍产出不合契约的维度/实体/关系）"
        )

    # 不变式（永远检查，无需配置）：无依据不得自称确定。
    # 后端已把"evidence 为空但 uncertain=false"的条目降级为存疑，因此正常不会触发；
    # 留着是为了万一哪天那道归一化被放宽时能被发现。
    for dimension in judged:
        if not dimension.get("evidence") and not dimension.get("uncertain"):
            problems.append(f"维度 {dimension['key']} 无依据却自称确定（未被标为存疑）")

    for want in expected.get("mustJudge", []):
        hit = any(
            dimension["key"] == want["key"]
            and not dimension.get("missing")
            and want.get("contains", "") in dimension["judgment"]
            for dimension in dimensions
        )
        if not hit:
            problems.append(
                f"维度 {want['key']} 未按期望判定（judgment 应含 {want.get('contains', '')!r}）"
            )

    if expected.get("requireRelations") and not body.get("relations"):
        problems.append("未产出任何关系（知识图谱只剩孤立节点）")

    names = {entity["name"] for entity in body.get("entities", [])}
    for name in expected.get("mustMentionEntities", []):
        if name not in names:
            problems.append(f"实体表未包含 {name!r}")

    return problems


def run(cases_name: str, only: str | None, verbose: bool) -> int:
    payload, cases = _load_cases(cases_name)
    if only:
        cases = [case for case in cases if case["id"] == only]
        if not cases:
            print(f"没有找到用例 {only}")
            return 1

    endpoint = str(payload.get("endpoint", ""))
    is_analyze = "/analyze" in endpoint

    print(f"用例文件 {cases_name}（回归集 {payload.get('version')}）")
    print(f"目标 Prompt {payload.get('prompt')} · 端点 {endpoint}")
    if is_analyze:
        print(
            f"用例数 {len(cases)}"
            "（known=名篇看七维是否都有依据，thin=信息不足看是否拒绝硬判）\n"
        )
    else:
        print(
            f"用例数 {len(cases)}"
            "（control=干净对照看误报，injected=注入错误看检出，clean=干净文本但看契约遵守）\n"
        )

    results: list[CaseResult] = []
    with TestClient(app, raise_server_exceptions=False) as client:
        health = client.get("/api/v1/health").json()
        print(f"后端就绪：status={health.get('status')} provider={health.get('llmProvider')}\n")

        for case in cases:
            if is_analyze:
                response = client.post("/api/v1/analyze", json={"text": case["source"]})
            else:
                options = {"produceTranslation": False}
                response = client.post(
                    "/api/v1/collate",
                    json={"text": case["source"], "options": options},
                )
            result = CaseResult(
                case_id=case["id"],
                kind=case["kind"],
                origin=case["origin"],
                passed=False,
            )

            if response.status_code != 200:
                detail = response.json().get("error", {})
                result.error = f"HTTP {response.status_code} {detail.get('code', '')} {detail.get('message', '')}"
            elif is_analyze:
                body = response.json()
                judged = [d for d in body["dimensions"] if not d.get("missing")]
                result.item_count = len(judged)
                result.dropped = body["droppedCount"]
                result.types = [d["key"] for d in judged]
                result.elapsed_ms = body["elapsedMs"]
                result.problems = _check_analyze_case(case, body)
                result.passed = not result.problems

                if verbose:
                    print(f"  [{case['id']}] 注入：{case['expected'].get('notes')}")
                    for dimension in body["dimensions"]:
                        mark = "未判断" if dimension.get("missing") else f"conf={dimension['confidence']}"
                        print(f"      {dimension['key']:12s} {mark} | {dimension['judgment']}")
                        for evidence in dimension.get("evidence", []):
                            print(f"          依据：{evidence}")
                    print(
                        f"      实体：{[e['name'] + '(' + e['kind'] + ')' for e in body['entities']]}"
                    )
                    print(f"      关系：{[r['source'] + '->' + r['target'] for r in body['relations']]}")
            else:
                body = response.json()
                result.item_count = len(body["items"])
                result.dropped = body["droppedCount"]
                result.types = [item["type"] for item in body["items"]]
                result.elapsed_ms = body["elapsedMs"]
                result.problems = _check_case(case, body)
                result.passed = not result.problems

                if verbose:
                    print(f"  [{case['id']}] 注入：{case['expected'].get('injected')}")
                    for item in body["items"]:
                        print(
                            f"      {item['type']} | {item['original']!r} -> {item['suggested']!r} "
                            f"| conf={item['confidence']} | {item['reason']}"
                        )
                    if not body["items"]:
                        print("      （无建议）")

            results.append(result)
            flag = "PASS" if result.passed else "FAIL"
            summary = result.error or (
                f"items={result.item_count} dropped={result.dropped} "
                f"types={'/'.join(result.types) or '-'} {result.elapsed_ms}ms"
            )
            print(f"{flag}  {result.case_id}  [{result.kind:8s}] {result.origin}")
            print(f"      {summary}")
            for problem in result.problems:
                print(f"      !! {problem}")

    passed = [r for r in results if r.passed]
    print(f"\n结果：{len(passed)}/{len(results)} 通过")
    failed = [r for r in results if not r.passed]
    if failed:
        print("未通过用例：" + "、".join(r.case_id for r in failed))
        print("提示：先看 expected 与上面的实际输出差异，再决定改 Prompt 还是改用例。")
    return 0 if not failed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Prompt 回归集执行器（需要真实密钥）")
    parser.add_argument("--cases", default=DEFAULT_CASES, help=f"用例文件名，默认 {DEFAULT_CASES}")
    parser.add_argument("--only", help="只跑某个用例，如 reg-005")
    parser.add_argument("--verbose", action="store_true", help="打印每条建议的内容")
    args = parser.parse_args()
    sys.exit(run(args.cases, args.only, args.verbose))


if __name__ == "__main__":
    main()
