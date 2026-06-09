"""Unit tests for MCP tool-result normalization (mcp-result-fidelity).

Pure-logic + duck-typed content-block handling; no real I/O — same style as
test_mcp_degradation.py. Covers the mcp-result-handling spec scenarios.
"""

import json
import types

import fleetent.integrations.mcp.client as mc


def _obj(**kw: object) -> types.SimpleNamespace:
    """An attribute bag mimicking an MCP SDK content object."""
    return types.SimpleNamespace(**kw)


# ── _block_to_text: text blocks (dict + object) ──────────────────────────────


def test_block_text_dict():
    assert mc._block_to_text({"type": "text", "text": "hello"}) == "hello"


def test_block_text_object():
    assert mc._block_to_text(_obj(type="text", text="hello")) == "hello"


# ── _block_to_text: image / audio markers (object has NO .text) ──────────────


def test_block_image_object_marker_no_crash():
    blk = _obj(type="image", data="aGVsbG8=", mimeType="image/png")
    out = mc._block_to_text(blk)
    assert "image" in out
    assert "image/png" in out
    assert "aGVsbG8=" not in out  # base64 payload not dumped


def test_block_image_dict_marker():
    out = mc._block_to_text({"type": "image", "data": "QUJDRA==", "mimeType": "image/jpeg"})
    assert "image/jpeg" in out
    assert "QUJDRA==" not in out


def test_block_audio_marker():
    out = mc._block_to_text({"type": "audio", "data": "AAAA", "mimeType": "audio/wav"})
    assert "audio/wav" in out


# ── _block_to_text: embedded resource ────────────────────────────────────────


def test_block_embedded_resource_text_inlined_dict():
    blk = {
        "type": "resource",
        "resource": {"uri": "file:///a", "mimeType": "text/plain", "text": "file body"},
    }
    assert mc._block_to_text(blk) == "file body"


def test_block_embedded_resource_text_inlined_object():
    blk = _obj(
        type="resource",
        resource=_obj(uri="file:///a", mimeType="text/plain", text="file body"),
    )
    assert mc._block_to_text(blk) == "file body"


def test_block_embedded_resource_blob_marker_no_dump():
    blk = {
        "type": "resource",
        "resource": {
            "uri": "file:///b.bin",
            "mimeType": "application/octet-stream",
            "blob": "QUFBQQ==",
        },
    }
    out = mc._block_to_text(blk)
    assert "resource" in out
    assert "QUFBQQ==" not in out  # blob payload not dumped


# ── _normalize_tool_result: aggregation ──────────────────────────────────────


def test_normalize_multiple_text_blocks_in_order():
    blocks = [{"type": "text", "text": "alpha"}, {"type": "text", "text": "beta"}]
    out = mc._normalize_tool_result(blocks, structured_content=None, is_error=False)
    assert "alpha" in out
    assert "beta" in out
    assert out.index("alpha") < out.index("beta")


def test_normalize_single_text_block_unchanged():
    out = mc._normalize_tool_result(
        [{"type": "text", "text": "ok"}], structured_content=None, is_error=False
    )
    assert out == "ok"


# ── _normalize_tool_result: isError ──────────────────────────────────────────


def test_normalize_is_error_marked_and_contains_text():
    out = mc._normalize_tool_result(
        [{"type": "text", "text": "bad arg: limit"}], structured_content=None, is_error=True
    )
    assert "bad arg: limit" in out
    assert out != "bad arg: limit"  # marked, not bare
    assert "error" in out.lower()


def test_normalize_success_not_marked_error():
    out = mc._normalize_tool_result(
        [{"type": "text", "text": "done"}], structured_content=None, is_error=False
    )
    assert out == "done"


# ── _normalize_tool_result: structuredContent precedence ─────────────────────


def test_normalize_structured_only_serialized():
    out = mc._normalize_tool_result([], structured_content={"count": 3}, is_error=False)
    assert json.loads(out) == {"count": 3}


def test_normalize_content_precedence_over_structured():
    out = mc._normalize_tool_result(
        [{"type": "text", "text": "hello"}], structured_content={"count": 3}, is_error=False
    )
    assert "hello" in out


def test_normalize_empty_result():
    assert mc._normalize_tool_result([], structured_content=None, is_error=False) == ""


def test_normalize_none_content():
    assert mc._normalize_tool_result(None, structured_content=None, is_error=False) == ""


# ── call-path wiring: _call_via_session (held SDK session, no network) ────────
# All transports collapse onto one path: the result object is normalized identically
# whether it came from stdio or streamable HTTP, so these exercise the shared seam.


class _FakeSession:
    def __init__(self, result: object) -> None:
        self._result = result

    async def call_tool(self, *args: object, **kwargs: object) -> object:
        return self._result


def _wire(monkeypatch, server_id: str, result: object, *, transport: str = "http") -> None:
    server = mc.McpServerConfig(id=server_id, transport=transport, url="http://x")
    monkeypatch.setitem(mc._server_registry, (None, server_id), server)
    monkeypatch.setitem(mc._active_sessions, (None, server_id), _FakeSession(result))


async def test_call_aggregates_blocks(monkeypatch):
    result = _obj(
        content=[_obj(type="text", text="a"), _obj(type="text", text="b")],
        structuredContent=None,
        isError=False,
    )
    _wire(monkeypatch, "svr", result)
    out = await mc._call_via_session("svr", "t", {})
    assert "a" in out
    assert "b" in out


async def test_call_surfaces_is_error(monkeypatch):
    result = _obj(
        content=[_obj(type="text", text="boom")],
        structuredContent=None,
        isError=True,
    )
    _wire(monkeypatch, "svr", result)
    out = await mc._call_via_session("svr", "t", {})
    assert "boom" in out
    assert "error" in out.lower()


async def test_call_structured_only(monkeypatch):
    result = _obj(content=[], structuredContent={"n": 5}, isError=False)
    _wire(monkeypatch, "svr", result)
    out = await mc._call_via_session("svr", "t", {})
    assert json.loads(out) == {"n": 5}


async def test_call_image_first_no_crash(monkeypatch):
    result = _obj(
        content=[_obj(type="image", data="aGVsbG8=", mimeType="image/png")],
        structuredContent=None,
        isError=False,
    )
    _wire(monkeypatch, "s", result, transport="stdio")
    out = await mc._call_via_session("s", "t", {})
    assert "image/png" in out  # marker; previously crashed on .text


async def test_call_multi_block_and_error(monkeypatch):
    result = _obj(
        content=[_obj(type="text", text="line1"), _obj(type="text", text="line2")],
        structuredContent=None,
        isError=True,
    )
    _wire(monkeypatch, "s", result, transport="stdio")
    out = await mc._call_via_session("s", "t", {})
    assert "line1" in out
    assert "line2" in out
    assert "error" in out.lower()
