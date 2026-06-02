"""Tests for tool-result truncation at the message write-back boundary (T4)."""

import fleetent.tool_registry as tr
import fleetent.tool_result_truncation as trt


def _nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


# ── truncate function + default threshold (group 2) ──────────────────────────


def test_within_threshold_returned_unchanged():
    s = "x" * 100
    assert trt.truncate_tool_result(s, max_bytes=1000) == s


def test_over_threshold_truncated_within_budget():
    s = "x" * 5000
    out = trt.truncate_tool_result(s, max_bytes=500)
    assert _nbytes(out) <= 500
    assert out != s


def test_default_threshold_used_when_none(monkeypatch):
    monkeypatch.setattr(trt, "MAX_TOOL_RESULT_BYTES", 200)
    s = "y" * 5000
    out = trt.truncate_tool_result(s)
    assert _nbytes(out) <= 200


def test_default_constant_is_about_40kb():
    assert trt.MAX_TOOL_RESULT_BYTES == 40_000


# ── head/tail + breadcrumb (group 3) ─────────────────────────────────────────


def test_truncation_keeps_head_and_tail_with_breadcrumb():
    s = "HEAD" + ("m" * 5000) + "TAIL"
    out = trt.truncate_tool_result(s, max_bytes=200)
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert "截断" in out  # breadcrumb present
    assert "字节" in out


def test_truncation_total_not_over_threshold():
    s = "a" * 10_000
    for limit in (120, 300, 1000):
        assert _nbytes(trt.truncate_tool_result(s, max_bytes=limit)) <= limit


# ── multibyte-safe cut (group 4) ─────────────────────────────────────────────


def test_multibyte_cut_falls_back_to_char_boundary():
    # Each Chinese char is 3 UTF-8 bytes; a byte budget landing mid-char must
    # back off to a full character, never producing invalid UTF-8.
    s = "中" * 5000
    out = trt.truncate_tool_result(s, max_bytes=205)
    out.encode("utf-8").decode("utf-8")  # must be valid (no exception)
    assert "�" not in out  # no replacement char from a broken sequence


# ── self_truncates metadata (group 5b) ───────────────────────────────────────


def test_self_truncates_recorded():
    @tr.tool(self_truncates=True)
    def _t_self() -> str:
        return "x"

    assert tr.is_self_truncating("_t_self") is True


def test_self_truncates_default_false():
    @tr.tool
    def _t_normal() -> str:
        return "x"

    assert tr.is_self_truncating("_t_normal") is False


def test_self_truncates_not_in_schema():
    @tr.tool(self_truncates=True)
    def _t_self_schema(query: str) -> str:
        return query

    schema = next(s for s in tr.get_schemas() if s["function"]["name"] == "_t_self_schema")
    props = schema["function"]["parameters"]["properties"]
    assert "self_truncates" not in props
    assert "query" in props


def test_run_code_declares_self_truncates():
    import fleetent.tools  # noqa: F401 — ensure tools are registered (import side effect)

    assert tr.is_self_truncating("run_code") is True
