#!/usr/bin/env python3
"""
fetch-assets.py — 查询中台账户余额并生成 XLSX 透视表。

依赖: openpyxl>=3.1.0
用法:
  python3 fetch-assets.py --names '["Alice","Bob"]'
  python3 fetch-assets.py --range '{"prefix":"ZYJDW00203-B","start":1,"end":79,"pad_width":0}'
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Hub wrapper 绝对路径。$SKILLS_DIR 由 fleetent 沙箱注入；
# 本地调试未注入时，从本脚本位置上溯 3 级到 skills 根目录兜底。
#
# NOTE (fleetent): 本脚本通过 wrapper shell-out 调用中台 MCP（middle__balance_get_account_balance）。
# fleetent 里 MCP 工具是 agent 循环里的直接调用，不在 run_code 沙箱内通过 CLI 发起；
# wrapper（middle-call.sh）当前是占位，未对接中台访问桥接，调用会以 exit 3 返回。
# 落地方式见 common-middle-system-query/scripts/middle-call.sh 头部说明。
# 另：中台 `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内。
_MIDDLE_WRAPPER = os.path.join(
    os.environ.get(
        "SKILLS_DIR",
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    ),
    "common-middle-system-query",
    "scripts",
    "middle-call.sh",
)

MAX_WORKERS = 10
REQUEST_TIMEOUT = 30
MAX_RETRIES = 2
MAX_NAMES_WITHOUT_CONFIRM = 100
RATE_LIMIT_CALLS = 50   # 每分钟最多发出的请求数（接口上限 60，留 10 buffer 给重试）
RATE_LIMIT_PERIOD = 60  # 滑动窗口（秒）


class RateLimiter:
    """滑动窗口速率限制器，线程安全。"""

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self._lock = threading.Lock()
        self._timestamps: list = []

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < self.period]
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                wait = self.period - (now - self._timestamps[0])
            time.sleep(max(wait, 0.01))


_rate_limiter = RateLimiter(RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD)


def expand_range(prefix: str, start: int, end: int, pad_width: int) -> list:
    if start > end:
        raise ValueError("范围起点不能大于终点")
    result = []
    for i in range(start, end + 1):
        num_str = str(i).zfill(pad_width) if pad_width > 0 else str(i)
        result.append(f"{prefix}{num_str}")
    return result


def parse_input(args) -> list:
    if args.names:
        names = json.loads(args.names)
    elif getattr(args, "range", None):
        r = json.loads(getattr(args, "range"))
        try:
            names = expand_range(r["prefix"], r["start"], r["end"], r.get("pad_width", 0))
        except ValueError as e:
            print(f"错误：{e}", flush=True)
            sys.exit(1)
    else:
        print("错误：必须提供 --names 或 --range 参数", flush=True)
        sys.exit(1)

    # 去重，保留首次出现顺序
    seen = set()
    deduped = []
    for name in names:
        if name not in seen:
            seen.add(name)
            deduped.append(name)

    if not deduped:
        print("错误：未提供账户名称", flush=True)
        sys.exit(1)

    if len(deduped) > MAX_NAMES_WITHOUT_CONFIRM:
        print(f"展开后共 {len(deduped)} 个账户，请确认后重新执行", flush=True)
        sys.exit(0)

    return deduped


def fetch_one(name: str) -> dict:
    for attempt in range(MAX_RETRIES + 1):
        try:
            _rate_limiter.acquire()
            result = subprocess.run(
                # 用 JSON 对象传参：保证纯数字账户名（罕见但可能）作为字符串
                # 透传给中台 MCP（middle__balance_get_account_balance），不被转 int
                ["bash", _MIDDLE_WRAPPER, "balance_get_account_balance",
                 json.dumps({"name": name}, ensure_ascii=False)],
                capture_output=True, text=True, timeout=REQUEST_TIMEOUT
            )
            if result.returncode != 0:
                if attempt < MAX_RETRIES:
                    continue
                err = result.stderr.strip() or f"非0退出码 ({result.returncode})"
                return {"ok": False, "name": name, "error": err}

            data = json.loads(result.stdout)

            if "account_id" not in data:
                return {"ok": False, "name": name, "error": "响应缺少 account_id 字段"}
            if "balances" not in data:
                return {"ok": False, "name": name, "error": "响应缺少 balances 字段"}
            if not isinstance(data["balances"], list):
                return {"ok": False, "name": name, "error": "balances 字段类型错误，期望数组"}
            if data.get("account_name") != name:
                return {
                    "ok": False, "name": name,
                    "error": f"名称不匹配：期望 {name!r}，返回 {data.get('account_name')!r}"
                }

            return {"ok": True, "name": name, "data": data}

        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return {"ok": False, "name": name, "error": f"请求超时（>{REQUEST_TIMEOUT}s）"}
        except json.JSONDecodeError as e:
            if attempt < MAX_RETRIES:
                continue
            return {"ok": False, "name": name, "error": f"JSON 解析失败：{e}"}
        except Exception as e:
            return {"ok": False, "name": name, "error": str(e)}

    return {"ok": False, "name": name, "error": "超过最大重试次数"}


def fetch_all(names: list) -> tuple:
    ok_results = []
    err_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_one, name): name for name in names}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result["ok"]:
                ok_results.append(result)
            else:
                err_results.append(result)

    name_order = {name: i for i, name in enumerate(names)}
    ok_results.sort(key=lambda r: name_order[r["name"]])
    err_results.sort(key=lambda r: name_order[r["name"]])

    return ok_results, err_results


def build_pivot(ok_results: list) -> tuple:
    row_order = []
    row_labels = {}
    col_order = []
    col_seen = set()
    cells = {}
    usdt_by_name = {}

    for result in ok_results:
        name = result["name"]
        data = result["data"]
        usdt_by_name[name] = float(data.get("total_value_usd") or 0.0)

        for balance in data.get("balances", []):
            if not balance.get("data"):
                continue
            type_desc = (
                balance.get("balance_type_desc")
                or balance.get("balance_type_name")
                or "Unknown"
            )
            rk = f"{name}\x1c{type_desc}"
            label = f"{name} - {type_desc}"

            for entry in balance["data"]:
                code = entry.get("code", "")
                if not code:
                    continue

                total = entry.get("total", "")
                if total == "":
                    continue

                if rk not in row_labels:
                    row_order.append(rk)
                    row_labels[rk] = label
                if code not in col_seen:
                    col_order.append(code)
                    col_seen.add(code)
                cells[(rk, code)] = total

    final_cols = (["BTC"] if "BTC" in col_seen else []) + [c for c in col_order if c != "BTC"]
    names_with_rows = {rk.split("\x1c")[0] for rk in row_order}
    empty_names = [r["name"] for r in ok_results if r["name"] not in names_with_rows]
    return row_order, row_labels, final_cols, cells, usdt_by_name, empty_names


def write_xlsx(row_order, row_labels, final_cols, cells, out_path: str,
               empty_names=None, err_results=None) -> None:
    empty_names = empty_names or []
    err_results = err_results or []
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "账户资产"

    header_fill  = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font  = Font(color="FFFFFF", bold=True, size=11)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin         = Side(style="thin", color="CCCCCC")
    border       = Border(left=thin, right=thin, top=thin, bottom=thin)
    empty_fill   = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    empty_font   = Font(color="808080", italic=True)
    err_fill     = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    err_font     = Font(color="C00000")

    has_note_col = bool(empty_names or err_results)
    headers = ["账户"] + final_cols + (["备注"] if has_note_col else [])
    note_col = len(headers)

    for c_idx, h in enumerate(headers, start=1):
        cell            = ws.cell(row=1, column=c_idx, value=h)
        cell.fill       = header_fill
        cell.font       = header_font
        cell.alignment  = header_align
        cell.border     = border

    for r_idx, rk in enumerate(row_order, start=2):
        label_cell           = ws.cell(row=r_idx, column=1, value=row_labels[rk])
        label_cell.border    = border
        label_cell.alignment = Alignment(vertical="center")
        for c_idx, code in enumerate(final_cols, start=2):
            raw  = cells.get((rk, code))
            cell = ws.cell(row=r_idx, column=c_idx)
            if raw is not None:
                try:
                    cell.value = float(raw)
                except (ValueError, TypeError):
                    cell.value = raw
            cell.border    = border
            cell.alignment = Alignment(horizontal="right", vertical="center")
        if has_note_col:
            ws.cell(row=r_idx, column=note_col).border = border

    next_row = len(row_order) + 2
    for i, name in enumerate(empty_names):
        r_idx = next_row + i
        for c_idx in range(1, len(headers) + 1):
            cell        = ws.cell(row=r_idx, column=c_idx)
            cell.fill   = empty_fill
            cell.border = border
        name_cell           = ws.cell(row=r_idx, column=1, value=name)
        name_cell.font      = empty_font
        name_cell.alignment = Alignment(vertical="center")
        note_cell           = ws.cell(row=r_idx, column=note_col, value="无持仓")
        note_cell.font      = empty_font
        note_cell.alignment = Alignment(vertical="center")

    next_row += len(empty_names)
    for i, r in enumerate(err_results):
        r_idx = next_row + i
        for c_idx in range(1, len(headers) + 1):
            cell        = ws.cell(row=r_idx, column=c_idx)
            cell.fill   = err_fill
            cell.border = border
        name_cell           = ws.cell(row=r_idx, column=1, value=r["name"])
        name_cell.font      = err_font
        name_cell.alignment = Alignment(vertical="center")
        note_cell             = ws.cell(row=r_idx, column=note_col, value=r["error"])
        note_cell.font        = err_font
        note_cell.alignment   = Alignment(vertical="center", wrap_text=True)

    for col in ws.columns:
        letter  = get_column_letter(col[0].column)
        max_len = max((len(str(c.value or "")) for c in col), default=0)
        ws.column_dimensions[letter].width = max(10, min(max_len + 3, 40))

    ws.freeze_panes             = "B2"
    ws.row_dimensions[1].height = 20

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main():
    parser = argparse.ArgumentParser(description="查询中台账户余额，生成 XLSX 透视表报告")
    parser.add_argument("--names", help='JSON 数组，如 \'["Alice","Bob"]\'')
    parser.add_argument("--range", help='JSON 范围，如 \'{"prefix":"B","start":1,"end":79,"pad_width":0}\'')
    args = parser.parse_args()

    names = parse_input(args)
    ok_results, err_results = fetch_all(names)

    lines = []

    if ok_results:
        lines.append("账户资金汇总：")
        for result in ok_results:
            usdt = float(result["data"].get("total_value_usd") or 0.0)
            lines.append(f"  {result['name']}：{usdt:,.2f} USDT")

    row_order, row_labels, final_cols, cells, _, empty_names = build_pivot(ok_results)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    month     = datetime.now().strftime("%Y-%m")
    out_dir   = os.environ.get("OUTBOUND_DIR", "/tmp")
    out_path  = f"{out_dir}/account-assets/{month}/account-assets-{timestamp}.xlsx"
    write_xlsx(row_order, row_labels, final_cols, cells, out_path,
               empty_names=empty_names, err_results=err_results)
    lines.append(f"已生成 Excel 文件：{out_path}")

    for r in err_results:
        lines.append(f"账户 {r['name']} 查询失败：{r['error']}")

    if len(names) > 1:
        ok_count   = len(ok_results)
        fail_count = len(err_results)
        if fail_count == 0:
            lines.append(f"批量查询完成：{ok_count} 成功 / 0 失败")
        else:
            fail_names = "、".join(r["name"] for r in err_results)
            lines.append(f"批量查询完成：{ok_count} 成功 / {fail_count} 失败（{fail_names} 查询失败）")

    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
