"""Integration: send_im_message `files` param + shared delivery kernel (§7).

send_im_message stays recipient-explicit (always medium-gated), so a human approval here
authorizes cross-scope artifact delivery: its `files` resolve through the same kernel as
send_file but with approved=True. Invalid entries degrade per-file (skipped, not aborted);
without `files` the behavior is unchanged.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.tools.registry import ToolContext


@pytest.fixture
def _exchange(tmp_path, monkeypatch):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    monkeypatch.setattr(artifact_exchange, "_state_db", db)
    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    monkeypatch.setattr(artifact_exchange, "_views_root", None)
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "report.xlsx").write_bytes(b"xlsx")
    artifact_exchange.register_server_root("gd", root)
    return root


def _ctx(scope_key: str = "K1"):
    sc = types.SimpleNamespace(platform="slack", sender_id="U1", chat_type="dm")
    return ToolContext(
        session_id="S1",
        scope_key=scope_key,
        session_context=sc,
        outbound_connectors={"slack": object()},
    )


async def test_send_im_message_no_files_unchanged(_exchange):
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=True)) as send_to,
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send_file_to,
    ):
        result = await send_im_message(target="U2", text="hi", tool_context=_ctx())
    send_to.assert_called_once()
    send_file_to.assert_not_called()
    assert "已发送" in result


async def test_send_im_message_delivers_cross_scope_artifact(_exchange):
    from fleetent.tools.builtin_tools import send_im_message

    # artifact owned by K1; the run is K2 → cross-scope. send_im_message is medium-gated, so
    # reaching here means a human approved → cross-scope delivery is authorized (approved=True).
    artifact_exchange.register(server_id="gd", rel_path="report.xlsx", scope_key="K1")
    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send_file_to,
    ):
        result = await send_im_message(
            target="U2",
            text="here",
            files=["/exchange/gd/report.xlsx"],
            tool_context=_ctx("K2"),
        )
    send_file_to.assert_called_once()
    assert str(_exchange / "report.xlsx") == send_file_to.call_args.args[3]
    assert "已发送" in result


async def test_send_im_message_skips_invalid_file_entry(_exchange):
    from fleetent.tools.builtin_tools import send_im_message

    artifact_exchange.register(server_id="gd", rel_path="report.xlsx", scope_key="K1")
    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=True)) as send_file_to,
    ):
        result = await send_im_message(
            target="U2",
            text="here",
            files=["/exchange/gd/report.xlsx", "/exchange/gd/missing.bin"],
            tool_context=_ctx("K1"),
        )
    # the valid one is delivered; the invalid entry is skipped, not aborting the call
    send_file_to.assert_called_once()
    assert "已发送" in result
