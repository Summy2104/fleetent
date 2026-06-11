"""Unit tests for the send_file builtin tool (sandbox-file-egress / sandbox-file-send).

send_file sends a workspace product back to the FIXED current sender (from
session_context), never a model-supplied recipient. No-approval iff
workspace_scope==session AND chat_type==dm AND session_context present; otherwise
fail-closed. Manager and connectors are mocked; no real DB/FastAPI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fleetent.im_gateway.normalizer import SessionContext
from fleetent.integrations.sandbox import Scope
from fleetent.tools.registry import ToolContext, get_risk_level


def _ctx(
    *,
    platform: str = "slack",
    chat_type: str = "dm",
    session_context: SessionContext | None = ...,  # type: ignore[assignment]
    connector: object | None = None,
) -> ToolContext:
    if session_context is ...:
        session_context = SessionContext(
            platform=platform, sender_id="U_SENDER", chat_type=chat_type
        )
    return ToolContext(
        session_id="sess-1",
        agent_name=None,
        session_context=session_context,
        outbound_connectors={platform: connector if connector is not None else object()},
    )


def _patch_manager(tmp_path: Path, scope: Scope = Scope.SESSION):
    """Patch _get_manager() to a mock whose scope/workspace_host_path use tmp_path."""
    manager = MagicMock()
    manager.scope = scope
    manager.workspace_host_path.return_value = tmp_path
    return patch("fleetent.tools.builtin_tools._get_manager", return_value=manager)


def test_send_file_registered_as_none_risk() -> None:
    import fleetent.tools.builtin_tools  # noqa: F401 — registration side effect

    assert get_risk_level("send_file") == "none"


def test_send_file_schema_exposes_only_path() -> None:
    import inspect

    from fleetent.tools.builtin_tools import send_file

    params = set(inspect.signature(send_file).parameters)
    # Only `path` is model-facing; tool_context is out-of-band (excluded from schema).
    assert params == {"path", "tool_context"}


# ── 2.1 happy path: fixed recipient ──────────────────────────────────────────


async def test_send_file_dm_session_scope_sends_to_fixed_recipient(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "report.pdf").write_bytes(b"%PDF")
    connector = object()
    with (
        _patch_manager(tmp_path),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send,
    ):
        result = await send_file(path="report.pdf", tool_context=_ctx(connector=connector))

    args = send.call_args
    assert args.args[0] == "slack"
    assert args.args[1] is connector
    assert args.args[2] == "U_SENDER"  # recipient from session_context, not a model arg
    assert args.args[3] == str(tmp_path / "report.pdf")
    # Result echoes the ACTUAL recipient.
    assert "slack:U_SENDER" in result


# ── 2.2 path translation / traversal ─────────────────────────────────────────


async def test_send_file_rejects_path_escape(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    with (
        _patch_manager(tmp_path),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send,
    ):
        result = await send_file(path="../../etc/passwd", tool_context=_ctx())

    send.assert_not_called()
    assert isinstance(result, str)
    assert "workspace" in result or "越界" in result or "路径" in result


async def test_send_file_missing_file_returns_text(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    with (
        _patch_manager(tmp_path),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send,
    ):
        result = await send_file(path="nope.pdf", tool_context=_ctx())

    send.assert_not_called()
    assert "不存在" in result or "找不到" in result


# ── 2.3 fail-closed matrix ───────────────────────────────────────────────────


async def test_send_file_channel_fail_closed(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "x.csv").write_bytes(b"x")
    with (
        _patch_manager(tmp_path),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send,
    ):
        result = await send_file(path="x.csv", tool_context=_ctx(chat_type="channel"))

    send.assert_not_called()
    assert "send_im_message" in result


async def test_send_file_agent_scope_fail_closed(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "x.csv").write_bytes(b"x")
    with (
        _patch_manager(tmp_path, scope=Scope.AGENT),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send,
    ):
        result = await send_file(path="x.csv", tool_context=_ctx())

    send.assert_not_called()
    assert "send_im_message" in result


async def test_send_file_no_session_context_fail_closed(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "x.csv").write_bytes(b"x")
    ctx = ToolContext(session_id="sess-1", session_context=None, outbound_connectors={})
    with (
        _patch_manager(tmp_path),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send,
    ):
        result = await send_file(path="x.csv", tool_context=ctx)

    send.assert_not_called()
    assert "会话发起人" in result or "无会话" in result


async def test_send_file_none_tool_context_fail_closed() -> None:
    from fleetent.tools.builtin_tools import send_file

    result = await send_file(path="x.csv", tool_context=None)
    assert isinstance(result, str)
    assert "会话发起人" in result or "无会话" in result


# ── 2.4 degradation ──────────────────────────────────────────────────────────


async def test_send_file_no_connector_returns_text(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "x.csv").write_bytes(b"x")
    ctx = ToolContext(
        session_id="sess-1",
        session_context=SessionContext(platform="slack", sender_id="U_S", chat_type="dm"),
        outbound_connectors={},
    )
    with _patch_manager(tmp_path):
        result = await send_file(path="x.csv", tool_context=ctx)

    assert "不支持" in result or "无可用" in result


async def test_send_file_delivery_failure_returns_text(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "x.csv").write_bytes(b"x")
    with (
        _patch_manager(tmp_path),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=False)),
    ):
        result = await send_file(path="x.csv", tool_context=_ctx())

    assert "失败" in result


async def test_send_file_never_raises_on_delivery_exception(tmp_path) -> None:
    from fleetent.tools.builtin_tools import send_file

    (tmp_path / "x.csv").write_bytes(b"x")
    with (
        _patch_manager(tmp_path),
        patch("fleetent.outbound.send_file_to", AsyncMock(side_effect=RuntimeError("net"))),
    ):
        result = await send_file(path="x.csv", tool_context=_ctx())

    assert isinstance(result, str)
    assert "失败" in result
