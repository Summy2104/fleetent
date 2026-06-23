"""Integration: send_im_message no-ops the current conversation (no-self-conversation-send).

A self-DM (target == sender, target_type == "user") issued from a CHANNEL conversation
targets the current-conversation participant, so the tool no-ops (the harness already
delivers the final reply) — nothing is sent, superseding the prior channel-pinning behavior.
A third-party send from the same channel is untouched (still delivered to the user target).
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.outbound import ConversationAddress, DeliveryReceipt
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
    (root / "chart.png").write_bytes(b"png-bytes")
    artifact_exchange.register_server_root("gd", root)
    return root


def _channel_ctx(scope_key="K1", sender="U1"):
    sc = types.SimpleNamespace(platform="slack", sender_id=sender, chat_type="channel")
    return ToolContext(
        session_id="S1",
        scope_key=scope_key,
        session_context=sc,
        outbound_connectors={"slack": object()},
        conversation_address=ConversationAddress(
            platform="slack",
            chat_id="C_CHAN",
            target_type="channel",
            thread_id="T_ROOT",
            user_id=sender,
            chat_type="channel",
        ),
    )


def _ok(kind):
    return DeliveryReceipt(ok=True, platform="slack", target="x", target_type="x", kind=kind)


async def test_channel_self_dm_is_noop(_exchange):
    from fleetent.tools.builtin_tools import send_im_message

    # File owned by the run's own scope (K1); the call targets the current sender (U1) from a
    # channel → current conversation → no-op (the harness delivers the reply), nothing sent.
    artifact_exchange.register(server_id="gd", rel_path="chart.png", scope_key="K1")
    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok("text"))) as send_to,
        patch(
            "fleetent.outbound.send_file_to", AsyncMock(return_value=_ok("file"))
        ) as send_file_to,
    ):
        result = await send_im_message(
            target="U1",  # the current sender
            text="here is the chart",
            files=["/exchange/gd/chart.png"],
            tool_context=_channel_ctx("K1", sender="U1"),
        )

    send_to.assert_not_called()
    send_file_to.assert_not_called()
    assert "未发送" in result


async def test_channel_third_party_send_not_pinned(_exchange):
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok("text"))) as send_to,
    ):
        result = await send_im_message(
            target="U2",  # a third party, not the sender
            text="fyi",
            tool_context=_channel_ctx("K1", sender="U1"),
        )

    # untouched: still a user DM to U2
    assert send_to.call_args.args[2] == "U2"
    assert send_to.call_args.kwargs["target_type"] == "user"
    assert "已发送" in result
