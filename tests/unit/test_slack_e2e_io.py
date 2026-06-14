"""Unit: helper 的 JSON 输出契约（单个对象 / 错误形态 / 退出码）。"""

from __future__ import annotations

import json

from tests.e2e.slack_autonomous._pure import (
    dump_json,
    error_result,
    exit_code_for,
    ok_result,
)


def test_ok_result_shape_and_exit_zero() -> None:
    r = ok_result(ts="123.45", channel="C1")
    assert r["ok"] is True
    assert r["ts"] == "123.45"
    assert exit_code_for(r) == 0


def test_error_result_shape_and_exit_nonzero() -> None:
    r = error_result("boom", detail="x")
    assert r["ok"] is False
    assert r["error"] == "boom"
    assert r["detail"] == "x"
    assert exit_code_for(r) == 1


def test_dump_json_emits_single_parseable_object() -> None:
    s = dump_json(ok_result(a=1, b="two"))
    parsed = json.loads(s)  # 必须是单个可解析对象
    assert parsed == {"ok": True, "a": 1, "b": "two"}
