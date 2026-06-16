#!/usr/bin/env python3
"""
query_txid_batch.py — 批量 TxID 查 NS r_transactions（到账状态反查）。

为什么需要：NS `/v1/r_transactions.txid` 是字符串精确匹配字段，
**不支持** comma-joined 多 TxID（如 `"hash1,hash2"` 会被当成一个字符串
做精确匹配，必然零命中）。本脚本封装"逐笔串行调用 + 结果聚合"，
agent 只需传一组 TxID，无需自己写 shell loop。

Usage:
    python3 query_txid_batch.py <sender_id> <txid1> [<txid2> ...]
    python3 query_txid_batch.py <sender_id> "<hash_long_or_comma_joined>"
    python3 query_txid_batch.py <sender_id> --txid-file <path>  # 一行一个
    python3 query_txid_batch.py <sender_id> ... --process-status uncompleted

输入兼容性（自动处理）：
- 单参数 `"hash1,hash2"` / `"hash1 hash2"` / `"hash1\\nhash2"` → 按分隔符切分
- 单参数 128 / 192 / 256 字符且都是 hex → 视为多个 64-char EVM TxID 拼接，
  自动按 64 切分（典型场景：用户复制 Slack 消息时把多个 TxID 黏在一起）
- 任何形态都会去重保序

输出（stdout 一段 JSON）：
    {
      "status": "ok",
      "total_txids": 2,
      "results": [
        {
          "txid": "40b2369...",
          "process_status": "completed",
          "hit_count": 1,
          "summary": [
            {
              "txid": "40b2369...",
              "to_account_name": "alpha-bn-spot",
              "from_account_name": "external",
              "amount": "1000.50",
              "currency": "USDT",
              "network": "ERC20",
              "transfer_time": "2026-05-15T10:23:11Z",
              "process_status": "completed",
              "process_instance_number": "20260515003"
            }
          ]
        },
        {
          "txid": "caa440f...",
          "process_status": "completed",
          "hit_count": 0,
          "summary": []
        }
      ]
    }

退出码：
    0   全部 TxID 查询完成（含部分零命中 / 错误）
    2   用法错误 / 缺参数
    3   sender_id 格式非法
    4   NS wrapper 不可执行
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any

NS_WRAPPER = os.path.join(
    os.environ.get(
        "SKILLS_DIR",
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
    "common-ns-system-query", "scripts", "ns-call.sh"
)

# 单笔 EVM TxID 标准长度（hex 字符数）
TXID_LEN = 64
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
SENDER_ID_RE = re.compile(r"^U[A-Z0-9]{8,}$")

# 汇总输出关心的字段（按 references/transactions-real-reconciliation.md）
SUMMARY_FIELDS = [
    "txid", "to_account_name", "from_account_name",
    "amount", "currency", "network",
    "transfer_time", "process_status", "process_instance_number",
]


def normalize_txids(raw_inputs: list[str]) -> list[str]:
    """把任意形态的输入归一化为干净的 TxID 列表，自动处理拼接 / 分隔符 / 去重保序。"""
    out: list[str] = []
    seen: set[str] = set()

    for item in raw_inputs:
        # 先按显式分隔符切分（逗号、空白、换行）
        pieces = re.split(r"[\s,]+", item.strip())
        for p in pieces:
            p = p.strip()
            if not p:
                continue
            # 如果是 64 整数倍长度的 hex 串，按 64 切分
            if len(p) > TXID_LEN and len(p) % TXID_LEN == 0 and HEX_RE.match(p):
                for i in range(0, len(p), TXID_LEN):
                    chunk = p[i:i + TXID_LEN]
                    if chunk not in seen:
                        seen.add(chunk)
                        out.append(chunk)
            else:
                if p not in seen:
                    seen.add(p)
                    out.append(p)
    return out


def query_one(sender_id: str, txid: str, process_status: str,
              timeout: float = 60.0) -> dict[str, Any]:
    """调一次 NS r_transactions 查单笔 TxID。"""
    query_params = json.dumps(
        {"txid": txid, "process_status": process_status,
         "page": 1, "page_size": 50},
        ensure_ascii=False,
    )
    cmd = [
        "bash", NS_WRAPPER, sender_id, "get", "/v1/r_transactions",
        f"query_params={query_params}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"txid": txid, "status": "error",
                "reason": "ns_wrapper_not_executable",
                "hint": NS_WRAPPER}
    except subprocess.TimeoutExpired:
        return {"txid": txid, "status": "error", "reason": "upstream_timeout"}

    if result.returncode != 0:
        return {
            "txid": txid,
            "status": "error",
            "reason": "upstream_error",
            "exit_code": result.returncode,
            "stderr": (result.stderr or "").strip()[:500],
        }

    # 解析 NS 返回
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"txid": txid, "status": "error", "reason": "invalid_json"}

    # NS r_transactions 返回结构通常是 {data: [...], total: N} 或 {results: [...]}
    rows = body.get("data") or body.get("results") or body.get("list") or []

    summary = []
    for row in rows:
        summary.append({
            field: row.get(field) for field in SUMMARY_FIELDS
        })

    return {
        "txid": txid,
        "status": "ok",
        "process_status": process_status,
        "hit_count": len(rows),
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量 TxID 查 NS r_transactions（到账反查）"
    )
    parser.add_argument("sender_id", help="Slack sender_id，格式 ^U[A-Z0-9]{8,}$")
    parser.add_argument("txids", nargs="*", help="TxID 列表，支持空格 / 逗号 / 换行混合，长 hash 自动按 64 切分")
    parser.add_argument("--txid-file", help="从文件读取 TxID（一行一个）")
    parser.add_argument(
        "--process-status",
        choices=["completed", "uncompleted"],
        default="completed",
        help="completed=已完成表（默认，到账查询用）；uncompleted=实时表（在途）",
    )
    parser.add_argument("--also-uncompleted", action="store_true",
                        help="先查 completed，零命中的 TxID 再查 uncompleted")
    args = parser.parse_args()

    if not SENDER_ID_RE.match(args.sender_id):
        print(json.dumps(
            {"status": "error", "reason": "invalid_sender_id",
             "hint": "sender_id 必须匹配 ^U[A-Z0-9]{8,}$"},
            ensure_ascii=False), file=sys.stderr)
        return 3

    raw: list[str] = list(args.txids)
    if args.txid_file:
        try:
            with open(args.txid_file) as f:
                raw.extend(f.read().splitlines())
        except OSError as e:
            print(json.dumps(
                {"status": "error", "reason": "txid_file_not_readable",
                 "hint": str(e)}, ensure_ascii=False), file=sys.stderr)
            return 2

    txids = normalize_txids(raw)
    if not txids:
        print(json.dumps(
            {"status": "error", "reason": "no_txids_provided"},
            ensure_ascii=False))
        return 2

    results = [query_one(args.sender_id, t, args.process_status) for t in txids]

    if args.also_uncompleted:
        # 对 completed 零命中的 TxID 再查 uncompleted
        for r in results:
            if r.get("status") == "ok" and r.get("hit_count") == 0:
                retry = query_one(args.sender_id, r["txid"], "uncompleted")
                if retry.get("hit_count", 0) > 0:
                    r["process_status"] = "uncompleted"
                    r["hit_count"] = retry["hit_count"]
                    r["summary"] = retry["summary"]

    print(json.dumps(
        {"status": "ok", "total_txids": len(txids), "results": results},
        ensure_ascii=False, indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
