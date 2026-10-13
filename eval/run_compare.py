"""对比实验执行器 —— 按 `EVAL.md §5` 对每个对象跑全量用例，产出 `*.raw.json` 交给 judge。

为什么走**真实 HTTP** 而不是 in-process 直调：本实验量的就是"用户实际拿到什么"，
必须如实经过 schema 闸门、原文定位、去重丢弃、限流这几层；绕过它们测出来的数字不能对外说。

两条可比性纪律（EVAL §5）：
- **强制 `produceTranslation=false`**：译文与校勘判定无关，关掉可减少变量与费用；
- 运行前先读 `/health`，把**当前生效的 Prompt 版本、规则开关、温度**记进结果文件——
  这三项过去靠人手记，漏记一次整批数字就不可追溯。

用法：
    python -m eval.run_compare --label mimo --base-url http://localhost:3001
    python -m eval.run_compare --label mimo --only case-003      # 只跑一段（调试用）
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import httpx

# 与 server/utils/schemas.py 的 MAX_TEXT_LEN 一致
MAX_TEXT_LEN = 5000
# 命中限流后的等待：后端是 30 req/min/IP 的滑动窗口，等满一个窗口再继续
RATE_LIMIT_WAIT_S = 61.0
# 单次 /collate 的总预算后端是 180s，前端留余量到 195s；执行器同样要比后端长
REQUEST_TIMEOUT_S = 200.0


def _health(client: httpx.Client) -> dict:
    response = client.get("/api/v1/health")
    response.raise_for_status()
    return response.json()


def _collate(client: httpx.Client, text: str) -> dict:
    """调用一次 /collate（关译文）。命中限流时等一个窗口再重试，**不静默跳过**。"""
    payload = {"text": text, "options": {"produceTranslation": False}}
    while True:
        response = client.post("/api/v1/collate", json=payload)
        if response.status_code == 429:
            print(f"    命中限流，等 {RATE_LIMIT_WAIT_S:.0f}s 后重试…")
            time.sleep(RATE_LIMIT_WAIT_S)
            continue
        if response.status_code != 200:
            detail = (response.json() or {}).get("error", {})
            raise RuntimeError(f"HTTP {response.status_code} {detail.get('code', '')} {detail.get('message', '')}")
        return response.json()


def run(args: argparse.Namespace) -> int:
    dataset_dir: Path = args.dataset
    cases = json.loads((dataset_dir / "cases.json").read_text(encoding="utf-8"))
    labels = json.loads((dataset_dir / "labels.json").read_text(encoding="utf-8"))
    labelled = {label["caseId"] for label in labels}

    todo = [case for case in cases if case["id"] in labelled]
    if args.only:
        todo = [case for case in todo if case["id"] == args.only]
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print("没有可跑的用例：dataset 里没有标注（先跑 python -m eval.self_check eval/dataset/）")
        return 1
    for case in todo:
        if len(case["source"]) > MAX_TEXT_LEN:
            print(f"用例 {case['id']} 超长（{len(case['source'])} 字），EVAL 要求 200–500 字，先修数据")
            return 1

    args.out.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    results: list[dict] = []

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=REQUEST_TIMEOUT_S) as client:
        health = _health(client)
        meta = {
            "label": args.label,
            "baseUrl": args.base_url,
            "llmProvider": health.get("llmProvider"),
            "promptVersion": health.get("collatePrompt"),
            "rulesEnabled": health.get("rulesEnabled"),
            "llmTemperature": health.get("llmTemperature"),
            "model": None,
            "startedAt": started.isoformat(timespec="seconds"),
        }
        print(
            f"对象 {args.label} | provider={meta['llmProvider']} | prompt={meta['promptVersion']} "
            f"| rules={meta['rulesEnabled']} | temperature={meta['llmTemperature']} | 用例 {len(todo)} 段"
        )

        for index, case in enumerate(todo, start=1):
            print(f"  [{index}/{len(todo)}] {case['id']} …")
            body = _collate(client, case["source"])
            meta["model"] = meta["model"] or body.get("model")
            results.append(
                {
                    "caseId": case["id"],
                    "items": body.get("items", []),
                    "droppedCount": body.get("droppedCount", 0),
                    "elapsedMs": body.get("elapsedMs", 0),
                    "model": body.get("model"),
                }
            )

    meta["model"] = meta["model"] or "unknown"
    meta["finishedAt"] = datetime.now().isoformat(timespec="seconds")
    meta["cases"] = results

    out_path = args.out / f"{args.label}.raw.json"
    out_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    total_items = sum(len(case["items"]) for case in results)
    total_dropped = sum(case["droppedCount"] for case in results)
    print(
        f"\n完成：{out_path}\n  {len(results)} 段 · 返回 {total_items} 条 · 丢弃 {total_dropped} 条 "
        f"· {meta['model']} · {meta['finishedAt']}"
    )
    print("下一步：python -m eval.judge --dataset eval/dataset/ --results eval/results/")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="对比实验执行器（EVAL §5）")
    parser.add_argument("--label", required=True, help="本对象的标签，用作文件名，如 mimo / siliconflow / ablate-rules")
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset"))
    parser.add_argument("--out", type=Path, default=Path("eval/results"))
    parser.add_argument("--base-url", default="http://localhost:3001")
    parser.add_argument("--only", help="只跑某一段（调试）")
    parser.add_argument("--limit", type=int, help="只跑前 N 段（调试）")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
