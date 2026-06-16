#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render 中台 V2 「账户流水」 JSON payload → .xlsx（纯本地 openpyxl）。

> NOTE (fleetent): 本脚本在 fleetent 下是 **纯本地渲染器**（不发起任何网络/MCP 调用）。
>   原 OpenClaw/Hermes 版本在脚本内 `subprocess.run(["mcpfast", ...])` 直接拉
>   中台 V2 动账流水（`transaction_list_account_transactions`）。fleetent 沙箱内
>   **没有 mcpfast**，MCP 工具调用由 agent 循环发起。又因中台 `middle` MCP server
>   不在 my-bot 已挂载的 9 个 MCP 面内（见适配指南 §2），动账流水当前无 fleetent MCP
>   对应能力 —— 详见 SKILL.md「依赖」段的 NOTE。
>
>   适配后的数据流（agent 取数 → 脚本渲染）：
>     1. agent 取得动账流水 JSON payload（接入中台桥接 / middle__<tool> 后），
>        落到一个临时 JSON 文件；
>     2. （可选）agent 调 `armada__armada_get path=/v1/accounts/digital_coin/category`
>        拿 market_id→名称映射，落到另一个临时 JSON 文件；
>     3. agent 用 `run_code` 跑本脚本：`--input <流水json> [--market-map-input <market json>]`
>        本脚本读 payload + 渲染 15 列 xlsx，输出一行状态 JSON。
>
>   `--input` 模式（下方实现）即此渲染入口；它从不触网，openpyxl 已在沙箱镜像预装。

V2 接口约束（来自中台官方文档，供 agent 取数时参考）：
  - 主接口：`transaction_list_account_transactions`（动账流水 V2）
  - **强制**至少传 `account_id` 或 `account_code`，**不接受** `account_name`
    单独查询（防止全表扫描）。`account_name` 需先经
    `balance_get_account_balance name=<X>` 解析出 `account_id` 再查流水。
  - 时间字段 `date` 已经是 UTC+0，不做时区转换。

输出列（15 列标准，用户指定）：
  1. 流水ID                ← id
  2. 账户名称 Account Name   ← account_name
  3. 账户代码 Account Code   ← account_code
  4. 币种 Coin              ← code_name
  5. 金额 Amount            ← derive：in_amount > 0 → +in_amount / out_amount > 0 → -out_amount
  6. 余额(变动后) Balance    ← balance_after
  7. 流向 Direction         ← derive：in_amount > 0 → 入账 / out_amount > 0 → 出账
  8. 出入账时间 Transfer Time ← date (UTC+0)
  9. 平台 Platform          ← market → 名称（NS armada_get 实时拉 / scripts/market_id_map.json 兜底）
 10. 描述 Description       ← description
 11. 关联NS流水 NS Flow ID  ← ns_flow_info.ns_flow_id
 12. 来源地址 From Address  ← from_address
 13. 目标地址 To Address    ← to_address
 14. TxID                  ← tx_id
 15. 更新时间 Updated At    ← update_datetime

CLI 用法（agent 先取数落 JSON 文件，再用 --input 渲染）：

    # 1) 用 account_id 标识（identifier 仅用于文件名 / 摘要回执）
    python3 render_xlsx.py \\
      --account-id 1204 \\
      --tx-start-time '2026-04-29 00:00:00' \\
      --tx-end-time   '2026-05-19 23:59:59' \\
      --input /tmp/transactions.json \\
      [--market-map-input /tmp/market_map.json] \\
      [--output outbound/动账流水/2026-05/middle_transactions_1204_xxx.xlsx]

    # 2) 用 account_code 标识
    python3 render_xlsx.py --account-code Mss0009 \\
      --tx-start-time ... --tx-end-time ... --input /tmp/transactions.json

    # 3) 用 account_name 标识（V2 主接口拒收 name，agent 取数时先经 balance
    #    解析出 account_id；--account-name 在这里仅用于文件名 / 摘要）
    python3 render_xlsx.py --account-name 'denghe_子账户2' \\
      --tx-start-time ... --tx-end-time ... --input /tmp/transactions.json

stdout 永远一行 JSON 状态：

    {"status":"ok","file":"<path>","rows":N,"identifier":"<X>","resolved_account_id":<id>}
    {"status":"error","reason":"<machine_code>", ...}

退出码：
    0  成功
    2  用法错误 / 参数缺失
    3  JSON 解析失败 / 结构未知
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPT_START = time.perf_counter()

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# ────────────────────────────────────────────────────────────────
# 常量
# ────────────────────────────────────────────────────────────────

RECORDS_KEY_CANDIDATES = ("results", "data", "list", "rows", "items")

# 中台动账流水相关工具名（供 agent 取数时调用，本脚本不再 shell-out 调用）：
#   主接口 transaction_list_account_transactions（兜底 transaction_get_account_transactions）
#   account_name → account_id 解析 balance_get_account_balance（参数名 name=）
TOOL_MAIN = "transaction_list_account_transactions"
TOOL_MAIN_FALLBACK = "transaction_get_account_transactions"
TOOL_BALANCE = "balance_get_account_balance"


# ────────────────────────────────────────────────────────────────
# 字面值工具（保留全精度，绝不走 float）
# ────────────────────────────────────────────────────────────────

def _is_zero_amount(s: Any) -> bool:
    s = str(s or "").strip().lstrip("+-")
    return s.strip("0").lstrip(".") in ("", "0")


def _pick(rec: dict[str, Any], candidates: list[str] | None) -> Any:
    """按候选顺序读第一个非空值；支持 dotted-path（如 'ns_flow_info.ns_flow_id'）。"""
    if not candidates:
        return ""
    for k in candidates:
        if "." in k:
            cur: Any = rec
            for part in k.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    cur = None
                    break
            if cur not in (None, ""):
                return cur
            continue
        if k in rec and rec[k] not in (None, ""):
            return rec[k]
    return ""


def _stringify(val: Any) -> Any:
    """保留中台原始字面值写入 xlsx 单元格。

    数值精度强约束：json.loads 已用 parse_float=str / parse_int=str，
    进入此函数前数字已是字符串字面值。float 兜底用 repr() 避免 str(float) 截断。
    """
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float):
        return repr(val)
    if isinstance(val, list):
        # tag 是 int 数组；用逗号拼字符串展示
        return ",".join(str(x) for x in val)
    return val


# ────────────────────────────────────────────────────────────────
# V2 接口字段派生
# ────────────────────────────────────────────────────────────────

def _signed_amount(rec: dict[str, Any]) -> str:
    """合成 signed amount：in_amount 正数原样；out_amount 加负号；都 0/空 返空。"""
    in_str = str(_pick(rec, ["in_amount"]) or "").strip()
    out_str = str(_pick(rec, ["out_amount"]) or "").strip()
    if in_str and not _is_zero_amount(in_str):
        return in_str.lstrip("+")
    if out_str and not _is_zero_amount(out_str):
        s = out_str.lstrip("+")
        return s if s.startswith("-") else f"-{s}"
    return ""


def _direction(rec: dict[str, Any]) -> str:
    """流向：in_amount > 0 → 入账 / out_amount > 0 → 出账 / 都 0/空 → 空。"""
    in_str = str(_pick(rec, ["in_amount"]) or "").strip()
    out_str = str(_pick(rec, ["out_amount"]) or "").strip()
    if in_str and not _is_zero_amount(in_str):
        return "入账"
    if out_str and not _is_zero_amount(out_str):
        return "出账"
    return ""


# ── market_id → 名称映射 ────────────────────────────
# 优先用 agent 经 `armada__armada_get path=/v1/accounts/digital_coin/category`
# 实时拉取的映射（每条记录 `id` = 数字 id，`market` = 名称），由 agent 落成
# JSON 文件后用 `--market-map-input` 传入；缺省时回落到静态
# scripts/market_id_map.json；未知 id 显示 `market#<id>`，不阻塞 xlsx 生成。
#
# > NOTE (fleetent): NS market 映射的实时拉取在 fleetent 下由 agent 发起
# >   `armada__armada_get`（双下划线工具名）完成，**不在本脚本内 shell-out mcpfast**。
# >   agent 把返回 JSON 落文件后用 --market-map-input 喂回本脚本。
_MARKET_MAP_CACHE: dict[str, str] = {}


def _load_static_market_map() -> dict[str, str]:
    p = Path(__file__).parent / "market_id_map.json"
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_market_map_payload(payload: Any) -> dict[str, str] | None:
    """从 armada_get /v1/accounts/digital_coin/category 的返回结构解析 {id: name}。

    NS 接口里每条记录 `id` 是数字 id、`market` 是平台名称
    （注意：跟动账记录里的 `market` 字段（id）字段名重了、意义相反 —— 这里取的是 NAME 的那个）。
    """
    records = _extract_records(payload)
    mapping: dict[str, str] = {}
    for rec in records:
        # 防御性多字段名：主名 id+market；兜底 market_id+market_name / id+name
        mid = rec.get("id") or rec.get("market_id")
        name = rec.get("market") or rec.get("market_name") or rec.get("name")
        if mid in (None, "") or not name:
            continue
        mapping[str(mid)] = str(name)
    return mapping or None


def _load_market_map_from_file(path: str) -> dict[str, str] | None:
    """读 agent 经 armada__armada_get 落盘的 market 映射 JSON 文件。"""
    try:
        raw = Path(path).read_text()
        payload = json.loads(raw or "", parse_int=str)
    except (OSError, json.JSONDecodeError):
        return None
    return _parse_market_map_payload(payload)


def _bootstrap_market_map(market_map_input: str | None) -> None:
    """把 market_id → name 映射加载进 `_MARKET_MAP_CACHE`。

    - 总是先读静态 `market_id_map.json` 作为基础；
    - 如 `--market-map-input` 给了 agent 经 armada__armada_get 拉来的映射文件，
      用它覆盖 / 扩充（armada 是 source of truth）；
    - 缺省（未传 --market-map-input）时只有静态表。
    """
    global _MARKET_MAP_CACHE
    base = _load_static_market_map()
    if not market_map_input:
        _MARKET_MAP_CACHE = base
        return
    ns_map = _load_market_map_from_file(market_map_input)
    # armada 是 source of truth，覆盖静态；读不到时只有 static
    _MARKET_MAP_CACHE = {**base, **(ns_map or {})}


def _market_name(rec: dict[str, Any]) -> str:
    mid = _pick(rec, ["market"])
    if mid in (None, ""):
        return ""
    return _MARKET_MAP_CACHE.get(str(mid), f"market#{mid}")


# ────────────────────────────────────────────────────────────────
# 输出列（用户指定的 13 列标准）
# ────────────────────────────────────────────────────────────────

COLUMNS: list[dict[str, Any]] = [
    {"header": "流水ID\nID",               "candidates": ["id"],                 "width": 14.0},
    {"header": "账户名称\nAccount Name",   "candidates": ["account_name"],       "width": 22.0},
    {"header": "账户代码\nAccount Code",   "candidates": ["account_code"],       "width": 14.0},
    {"header": "币种\nCoin",               "candidates": ["code_name"],          "width": 12.0},
    {"header": "金额\nAmount",             "derive":     _signed_amount,         "width": 22.0},
    {"header": "余额(变动后)\nBalance After","candidates": ["balance_after"],     "width": 22.0},
    {"header": "流向\nDirection",          "derive":     _direction,             "width": 10.0},
    {"header": "出入账时间(UTC+0)\nTransfer Time", "candidates": ["date"],       "width": 22.0},
    {"header": "平台\nPlatform",           "derive":     _market_name,           "width": 14.0},
    {"header": "描述\nDescription",        "candidates": ["description"],        "width": 30.0},
    {"header": "关联NS流水\nNS Flow ID",   "candidates": ["ns_flow_info.ns_flow_id"], "width": 22.0},
    {"header": "来源地址\nFrom Address",   "candidates": ["from_address"],       "width": 38.0},
    {"header": "目标地址\nTo Address",     "candidates": ["to_address"],         "width": 38.0},
    {"header": "TxID",                     "candidates": ["tx_id"],              "width": 32.0},
    {"header": "更新时间\nUpdated At",     "candidates": ["update_datetime"],    "width": 22.0},
]


# ────────────────────────────────────────────────────────────────
# 取数层
# ────────────────────────────────────────────────────────────────
#
# > NOTE (fleetent): 原 OpenClaw/Hermes 版本在此处通过 hub wrapper
# >   (common-middle-system-query/scripts/middle-call.sh) shell-out `mcpfast`
# >   直接拉中台 V2 动账流水 / balance 解析。fleetent 沙箱内没有 mcpfast，
# >   且中台 `middle` MCP server 不在 my-bot 9 个 MCP 面内（见适配指南 §2），
# >   因此本脚本不再发起任何取数调用 —— 改由 agent 用 MCP 工具取数后经
# >   `--input` / `--market-map-input` 喂回本脚本渲染。
# >   接入中台桥接 / `middle__<tool>` 能力后，agent 取数流程见 SKILL.md「依赖」段。

_TIMING: dict[str, int] = {}


def _record_ms(key: str, ms: int) -> None:
    _TIMING[key] = _TIMING.get(key, 0) + ms


# ────────────────────────────────────────────────────────────────
# JSON 解析
# ────────────────────────────────────────────────────────────────

def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in RECORDS_KEY_CANDIDATES:
            if key in payload and isinstance(payload[key], list):
                return [r for r in payload[key] if isinstance(r, dict)]
        if isinstance(payload.get("data"), dict):
            inner = payload["data"]
            for key in RECORDS_KEY_CANDIDATES:
                if key in inner and isinstance(inner[key], list):
                    return [r for r in inner[key] if isinstance(r, dict)]
    return []


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_") or "account"


# ────────────────────────────────────────────────────────────────
# xlsx 渲染
# ────────────────────────────────────────────────────────────────

def render(payload: Any, output_path: Path, identifier: str,
           resolved_account_id: int | None = None,
           emit_timing: bool = False) -> int:
    t_build0 = time.perf_counter()
    records = _extract_records(payload)

    wb = Workbook()
    ws = wb.active
    ws.title = "中台动账流水"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4472C4")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="000000")
    header_border = Border(top=thin, bottom=thin, left=thin, right=thin)

    for col_idx, col in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col["header"])
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = header_border
        ws.column_dimensions[get_column_letter(col_idx)].width = col["width"]

    data_align = Alignment(vertical="center", wrap_text=False)
    for idx, rec in enumerate(records, start=1):
        row_idx = idx + 1
        for col_idx, col in enumerate(COLUMNS, start=1):
            if "derive" in col:
                val = col["derive"](rec)
            else:
                val = _pick(rec, col.get("candidates"))
            cell = ws.cell(row=row_idx, column=col_idx, value=_stringify(val))
            cell.alignment = data_align

    ws.freeze_panes = "A2"
    t_build1 = time.perf_counter()
    _record_ms("xlsx_build_ms", int((t_build1 - t_build0) * 1000))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    t_save0 = time.perf_counter()
    wb.save(output_path)
    _record_ms("xlsx_save_ms", int((time.perf_counter() - t_save0) * 1000))

    out: dict[str, Any] = {
        "status": "ok",
        "file": str(output_path),
        "rows": len(records),
        "identifier": identifier,
    }
    if resolved_account_id is not None:
        out["resolved_account_id"] = resolved_account_id
    if emit_timing:
        _record_ms("total_ms", int((time.perf_counter() - _SCRIPT_START) * 1000))
        out["timing"] = dict(_TIMING)
    print(json.dumps(out, ensure_ascii=False))
    return 0


# ────────────────────────────────────────────────────────────────
# 命名 / CLI
# ────────────────────────────────────────────────────────────────

def _yyyymmdd(s: str | None) -> str | None:
    if not s:
        return None
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", s)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else None


def _default_output(identifier: str, start: str | None, end: str | None) -> Path:
    today = datetime.utcnow().strftime("%Y%m%d")
    safe = _safe_filename(identifier)
    s, e = _yyyymmdd(start), _yyyymmdd(end)
    if s and e:
        fname = f"middle_transactions_{safe}_{s}_{e}.xlsx"
    else:
        fname = f"middle_transactions_{safe}_{today}.xlsx"
    return Path(os.environ.get("OUTPUT_DIR", os.getcwd())) / fname


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Render 中台 V2 动账流水 JSON payload → 15-column .xlsx（纯本地）。",
    )
    parser.add_argument("--account-name",
                        help="账户名称标识（仅用于文件名 / 摘要回执；V2 主接口拒收 name，"
                             "agent 取数时需先经 balance 解析成 account_id）")
    parser.add_argument("--account-id", type=int, help="账户数字 id 标识；最精确（推荐）")
    parser.add_argument("--account-code", help="账户编码标识，如 Mss0009；与 id 等价")
    parser.add_argument("--tx-start-time", help='开始时间 "YYYY-MM-DD HH:mm:ss" (UTC+0)，用于文件名')
    parser.add_argument("--tx-end-time",   help='结束时间 "YYYY-MM-DD HH:mm:ss" (UTC+0)，用于文件名')
    parser.add_argument("--ordering", default="-date")
    parser.add_argument("--page-size", default=200, type=int)
    parser.add_argument("--output", help="输出 .xlsx 路径")
    parser.add_argument("--input", required=True,
                        help="动账流水 JSON 文件（agent 取数后落盘）；本脚本只读不触网")
    parser.add_argument("--market-map-input",
                        help="market_id→名称映射 JSON 文件（agent 经 armada__armada_get "
                             "path=/v1/accounts/digital_coin/category 取得后落盘）；"
                             "缺省时回落到静态 scripts/market_id_map.json")
    parser.add_argument("--timing", action="store_true",
                        help="stdout/stderr JSON 末尾附 timing 段")
    parser.add_argument("--inspect-fields", action="store_true",
                        help="诊断模式：只打印 records[0] 的字段名 + 命中报告，不写 xlsx，不输出 values")
    args = parser.parse_args(argv)

    # ── market 映射加载（agent 经 armada__armada_get 取得后用 --market-map-input 传入）──
    _bootstrap_market_map(args.market_map_input)

    # ── 参数校验（标识仅用于文件名 / 摘要，三选一保持原语义）────────
    ids_given = [x for x in (args.account_name, args.account_id, args.account_code) if x not in (None, "")]
    if not ids_given:
        print(json.dumps({"status": "error", "reason": "missing_account_identifier",
                          "hint": "需要 --account-name / --account-id / --account-code 三选一"},
                         ensure_ascii=False),
              file=sys.stderr, flush=True)
        return 2
    if len(ids_given) > 1:
        print(json.dumps({"status": "error", "reason": "multiple_account_identifiers",
                          "hint": "三个标识参数只能传一个"},
                         ensure_ascii=False),
              file=sys.stderr, flush=True)
        return 2

    # ── 决定 identifier（用于文件名）────────────────────────────
    resolved_account_id: int | None = None
    identifier: str
    if args.account_id is not None:
        identifier = str(args.account_id)
    elif args.account_code:
        identifier = args.account_code
    else:
        identifier = args.account_name

    # ── 取数（纯本地读 agent 落盘的 JSON）─────────────────────────
    try:
        raw = Path(args.input).read_text()
    except OSError as e:
        print(json.dumps({"status": "error", "reason": "input_file_unreadable", "detail": str(e)}),
              file=sys.stderr, flush=True)
        return 2

    # ── JSON 解析（parse_float=str / parse_int=str 锁字面值）──────
    t_json0 = time.perf_counter()
    try:
        payload = json.loads(raw or "", parse_float=str, parse_int=str)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "reason": "invalid_json", "detail": str(e)}),
              file=sys.stderr, flush=True)
        return 3
    _record_ms("json_parse_ms", int((time.perf_counter() - t_json0) * 1000))

    # ── 字段诊断模式 ───────────────────────────────
    if args.inspect_fields:
        records = _extract_records(payload)
        if not records:
            print(json.dumps({"status": "ok", "rows": 0,
                              "note": "payload 解析出 0 条记录，无法诊断字段"},
                             ensure_ascii=False))
            return 0
        sample = records[0]
        hit_report = []
        for col in COLUMNS:
            if "derive" in col:
                hit_report.append({"column": col["header"].splitlines()[0],
                                   "kind": "derived"})
                continue
            cands = col.get("candidates") or []
            hit = next((k for k in cands if _pick(sample, [k]) not in (None, "")), None)
            hit_report.append({"column": col["header"].splitlines()[0],
                               "kind": "lookup",
                               "hit_field": hit, "tried": cands})
        result = {
            "status": "ok",
            "rows_in_payload": len(records),
            "first_record_keys": sorted(sample.keys()),
            "column_hit_report": hit_report,
        }
        if args.timing:
            _record_ms("total_ms", int((time.perf_counter() - _SCRIPT_START) * 1000))
            result["timing"] = dict(_TIMING)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # ── 落盘 ─────────────────────────────────────────
    output_path = Path(args.output) if args.output else _default_output(
        identifier, args.tx_start_time, args.tx_end_time)
    return render(payload, output_path, identifier,
                  resolved_account_id=resolved_account_id,
                  emit_timing=args.timing)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
