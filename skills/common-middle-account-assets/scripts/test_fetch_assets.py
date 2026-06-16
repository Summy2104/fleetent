"""单元测试 — fetch-assets.py"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

# fetch-assets.py 含连字符，无法直接 import，用 importlib 加载
_spec = importlib.util.spec_from_file_location(
    "fetch_assets",
    os.path.join(os.path.dirname(__file__), "fetch-assets.py")
)
fa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fa)


# ── RateLimiter ───────────────────────────────────────────────

def test_rate_limiter_allows_up_to_max():
    rl = fa.RateLimiter(max_calls=5, period=60)
    for _ in range(5):
        rl.acquire()  # 不应阻塞
    assert len(rl._timestamps) == 5

def test_rate_limiter_blocks_on_exceed(monkeypatch):
    # 用极短窗口，验证超出限额时确实等待
    import time
    rl = fa.RateLimiter(max_calls=2, period=0.2)
    rl.acquire()
    rl.acquire()
    t0 = time.monotonic()
    rl.acquire()  # 第3次应等待窗口滑过
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.1  # 至少等了一部分窗口

# ── expand_range ──────────────────────────────────────────────

def test_expand_range_basic():
    assert fa.expand_range("ZYJDW00203-B", 1, 3, 0) == [
        "ZYJDW00203-B1", "ZYJDW00203-B2", "ZYJDW00203-B3"
    ]

def test_expand_range_with_padding():
    assert fa.expand_range("B", 1, 3, 2) == ["B01", "B02", "B03"]

def test_expand_range_single():
    assert fa.expand_range("PREFIX-", 5, 5, 0) == ["PREFIX-5"]

def test_expand_range_reverse_raises():
    with pytest.raises(ValueError, match="起点不能大于终点"):
        fa.expand_range("B", 10, 1, 0)


# ── parse_input ───────────────────────────────────────────────

def _args(names=None, range_=None):
    return argparse.Namespace(names=names, **{"range": range_})

def test_parse_input_names_list():
    result = fa.parse_input(_args(names='["Alice","Bob","Carol"]'))
    assert result == ["Alice", "Bob", "Carol"]

def test_parse_input_range():
    result = fa.parse_input(_args(range_='{"prefix":"B","start":1,"end":3,"pad_width":0}'))
    assert result == ["B1", "B2", "B3"]

def test_parse_input_range_with_padding():
    result = fa.parse_input(_args(range_='{"prefix":"B","start":1,"end":3,"pad_width":2}'))
    assert result == ["B01", "B02", "B03"]

def test_parse_input_dedup_preserves_order():
    result = fa.parse_input(_args(names='["Alice","Bob","Alice","Carol"]'))
    assert result == ["Alice", "Bob", "Carol"]

def test_parse_input_reverse_range_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        fa.parse_input(_args(range_='{"prefix":"B","start":5,"end":1,"pad_width":0}'))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "起点不能大于终点" in captured.out

def test_parse_input_over_100_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        fa.parse_input(_args(range_='{"prefix":"B","start":1,"end":101,"pad_width":0}'))
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "101" in captured.out
    assert "确认" in captured.out

def test_parse_input_empty_names_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        fa.parse_input(_args(names='[]'))
    assert exc.value.code == 1

def test_parse_input_no_args_exits():
    with pytest.raises(SystemExit):
        fa.parse_input(_args())


# ── fetch_one ─────────────────────────────────────────────────

def _mock_run(stdout_data: dict, returncode: int = 0, stderr: str = ""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = json.dumps(stdout_data)
    m.stderr = stderr
    return m

VALID_RESPONSE = {
    "account_id": 49,
    "account_name": "Alice",
    "total_value_usd": 1000.0,
    "balances": []
}

def test_fetch_one_success():
    with patch("subprocess.run", return_value=_mock_run(VALID_RESPONSE)):
        result = fa.fetch_one("Alice")
    assert result["ok"] is True
    assert result["name"] == "Alice"
    assert result["data"]["account_id"] == 49

def test_fetch_one_name_mismatch():
    resp = {**VALID_RESPONSE, "account_name": "Wrong"}
    with patch("subprocess.run", return_value=_mock_run(resp)):
        result = fa.fetch_one("Alice")
    assert result["ok"] is False
    assert "名称不匹配" in result["error"]

def test_fetch_one_missing_balances():
    resp = {"account_id": 49, "account_name": "Alice"}
    with patch("subprocess.run", return_value=_mock_run(resp)):
        result = fa.fetch_one("Alice")
    assert result["ok"] is False
    assert "balances" in result["error"]

def test_fetch_one_missing_account_id():
    resp = {"account_name": "Alice", "balances": []}
    with patch("subprocess.run", return_value=_mock_run(resp)):
        result = fa.fetch_one("Alice")
    assert result["ok"] is False
    assert "account_id" in result["error"]

def test_fetch_one_balances_not_list():
    resp = {**VALID_RESPONSE, "balances": "invalid"}
    with patch("subprocess.run", return_value=_mock_run(resp)):
        result = fa.fetch_one("Alice")
    assert result["ok"] is False

def test_fetch_one_nonzero_exit_retries_and_fails():
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = "connection refused"
    with patch("subprocess.run", return_value=m) as mock_run:
        result = fa.fetch_one("Alice")
    # MAX_RETRIES=2, 所以应尝试 3 次
    assert mock_run.call_count == fa.MAX_RETRIES + 1
    assert result["ok"] is False

def test_fetch_one_timeout_retries_and_fails():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=30)) as mock_run:
        result = fa.fetch_one("Alice")
    assert mock_run.call_count == fa.MAX_RETRIES + 1
    assert result["ok"] is False
    assert "超时" in result["error"]

def test_fetch_one_invalid_json_retries_and_fails():
    m = MagicMock()
    m.returncode = 0
    m.stdout = "not-json"
    m.stderr = ""
    with patch("subprocess.run", return_value=m) as mock_run:
        result = fa.fetch_one("Alice")
    assert mock_run.call_count == fa.MAX_RETRIES + 1
    assert result["ok"] is False
    assert "JSON" in result["error"]


# ── fetch_all ─────────────────────────────────────────────────

def _make_fetch_one_side_effect(results_map: dict):
    def _side_effect(name):
        return results_map[name]
    return _side_effect

def test_fetch_all_all_success():
    results_map = {
        "Alice": {"ok": True, "name": "Alice", "data": {**VALID_RESPONSE, "account_name": "Alice"}},
        "Bob":   {"ok": True, "name": "Bob",   "data": {**VALID_RESPONSE, "account_name": "Bob"}},
    }
    with patch.object(fa, "fetch_one", side_effect=_make_fetch_one_side_effect(results_map)):
        ok, err = fa.fetch_all(["Alice", "Bob"])
    assert len(ok) == 2
    assert len(err) == 0
    assert ok[0]["name"] == "Alice"
    assert ok[1]["name"] == "Bob"

def test_fetch_all_partial_failure():
    results_map = {
        "Alice": {"ok": True,  "name": "Alice", "data": {**VALID_RESPONSE, "account_name": "Alice"}},
        "Bad":   {"ok": False, "name": "Bad",   "error": "not found"},
        "Carol": {"ok": True,  "name": "Carol", "data": {**VALID_RESPONSE, "account_name": "Carol"}},
    }
    with patch.object(fa, "fetch_one", side_effect=_make_fetch_one_side_effect(results_map)):
        ok, err = fa.fetch_all(["Alice", "Bad", "Carol"])
    assert len(ok) == 2
    assert len(err) == 1
    assert err[0]["name"] == "Bad"

def test_fetch_all_preserves_order():
    names = ["C", "A", "B"]
    results_map = {n: {"ok": True, "name": n, "data": {**VALID_RESPONSE, "account_name": n}} for n in names}
    with patch.object(fa, "fetch_one", side_effect=_make_fetch_one_side_effect(results_map)):
        ok, _ = fa.fetch_all(names)
    assert [r["name"] for r in ok] == ["C", "A", "B"]


# ── build_pivot ───────────────────────────────────────────────

def _ok(name, balances):
    return {
        "ok": True, "name": name,
        "data": {"account_id": 1, "account_name": name,
                 "total_value_usd": 5000.0, "balances": balances}
    }

def _balance(type_desc, coins):
    return {"balance_type_desc": type_desc, "data": coins}

def _coin(code, total, value_usdt):
    return {"code": code, "total": total, "value_usdt": value_usdt}

def test_build_pivot_basic():
    results = [_ok("Alice", [_balance("币币账户", [
        _coin("BTC", 1.5, 100000.0),
        _coin("ETH", 10.0, 30000.0),
    ])])]
    row_order, row_labels, final_cols, cells, usdt_by_name, _ = fa.build_pivot(results)
    assert "Alice\x1c币币账户" in row_order
    assert row_labels["Alice\x1c币币账户"] == "Alice - 币币账户"
    assert final_cols[0] == "BTC"
    assert cells[("Alice\x1c币币账户", "BTC")] == 1.5
    assert cells[("Alice\x1c币币账户", "ETH")] == 10.0

def test_build_pivot_includes_all_positions():
    results = [_ok("Alice", [_balance("币币账户", [
        _coin("BTC", 1.0, 100000.0),
        _coin("DUST", 0.001, 1.0),
    ])])]
    _, _, final_cols, cells, _, _ = fa.build_pivot(results)
    assert "DUST" in final_cols
    assert "BTC" in final_cols

def test_build_pivot_empty_data_skipped():
    results = [_ok("Alice", [{"balance_type_desc": "资金账户", "data": []}])]
    row_order, _, _, _, _, _ = fa.build_pivot(results)
    assert len(row_order) == 0

def test_build_pivot_btc_first_even_if_seen_later():
    results = [_ok("Alice", [_balance("币币账户", [
        _coin("ETH", 5.0, 10000.0),
        _coin("BTC", 1.0, 80000.0),
        _coin("USDT", 1000.0, 1000.0),
    ])])]
    _, _, final_cols, _, _, _ = fa.build_pivot(results)
    assert final_cols[0] == "BTC"

def test_build_pivot_multiple_accounts():
    results = [
        _ok("Alice", [_balance("币币账户", [_coin("BTC", 1.0, 80000.0)])]),
        _ok("Bob",   [_balance("赚币-活期", [_coin("ETH", 5.0, 15000.0)])]),
    ]
    row_order, row_labels, final_cols, cells, _, _ = fa.build_pivot(results)
    assert len(row_order) == 2
    assert "BTC" in final_cols
    assert "ETH" in final_cols

def test_build_pivot_no_value_usdt_included():
    results = [_ok("Alice", [_balance("币币账户", [
        {"code": "XYZ", "total": 100.0, "value_usdt": None},
    ])])]
    _, _, final_cols, _, _, _ = fa.build_pivot(results)
    assert "XYZ" in final_cols


# ── write_xlsx ────────────────────────────────────────────────

def test_write_xlsx_creates_file_with_correct_structure():
    row_order = ["Alice\x1c币币账户"]
    row_labels = {"Alice\x1c币币账户": "Alice - 币币账户"}
    final_cols = ["BTC", "ETH"]
    cells = {("Alice\x1c币币账户", "BTC"): 1.5}

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "sub", "test.xlsx")
        fa.write_xlsx(row_order, row_labels, final_cols, cells, out_path)

        assert os.path.exists(out_path)

        wb = openpyxl.load_workbook(out_path)
        ws = wb.active
        assert ws.title == "账户资产"
        assert ws.cell(row=1, column=1).value == "账户"
        assert ws.cell(row=1, column=2).value == "BTC"
        assert ws.cell(row=1, column=3).value == "ETH"
        assert ws.cell(row=2, column=1).value == "Alice - 币币账户"
        assert ws.cell(row=2, column=2).value == 1.5
        assert ws.cell(row=2, column=3).value is None

def test_write_xlsx_creates_parent_dirs():
    row_order = ["R\x1cT"]
    row_labels = {"R\x1cT": "R - T"}
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "a", "b", "c", "out.xlsx")
        fa.write_xlsx(row_order, row_labels, ["BTC"], {("R\x1cT", "BTC"): 1.0}, out_path)
        assert os.path.exists(out_path)

def test_write_xlsx_err_results_appended():
    row_order = ["Alice\x1c币币账户"]
    row_labels = {"Alice\x1c币币账户": "Alice - 币币账户"}
    final_cols = ["BTC"]
    cells = {("Alice\x1c币币账户", "BTC"): 1.0}
    err_results = [{"name": "BadName", "error": "账户不存在"}]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "test.xlsx")
        fa.write_xlsx(row_order, row_labels, final_cols, cells, out_path, err_results=err_results)

        wb = openpyxl.load_workbook(out_path)
        ws = wb.active
        # 表头含"备注"列
        assert ws.cell(row=1, column=3).value == "备注"
        # 失败账户在 row 3（row 2 是 Alice）
        assert ws.cell(row=3, column=1).value == "BadName"
        assert ws.cell(row=3, column=3).value == "账户不存在"

def test_write_xlsx_all_failed_generates_file():
    err_results = [
        {"name": "B1", "error": "账户不存在"},
        {"name": "B2", "error": "JSON 解析失败"},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "test.xlsx")
        fa.write_xlsx([], {}, [], {}, out_path, err_results=err_results)

        assert os.path.exists(out_path)
        wb = openpyxl.load_workbook(out_path)
        ws = wb.active
        assert ws.cell(row=1, column=1).value == "账户"
        assert ws.cell(row=1, column=2).value == "备注"
        assert ws.cell(row=2, column=1).value == "B1"
        assert ws.cell(row=3, column=1).value == "B2"
