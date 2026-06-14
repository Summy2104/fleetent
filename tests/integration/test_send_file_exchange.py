"""Integration: send_file delivers an /exchange artifact end-to-end (§6.3).

A run sending an own-scope /exchange artifact resolves it through the ledger and delivers
the real host file to the harness-fixed recipient. send_file is never approval-gated
(approval-boundary-redesign) and therefore has no cross-scope escape: an artifact owned by
another scope is hard-refused (resolve with approved=False), pointing to send_im_message.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.integrations.sandbox import Scope
from fleetent.outbound import DeliveryReceipt
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


def _ctx(scope_key: str):
    sc = types.SimpleNamespace(platform="slack", sender_id="U1", chat_type="dm")
    return ToolContext(
        session_id="S1",
        scope_key=scope_key,
        session_context=sc,
        outbound_connectors={"slack": object()},
    )


async def test_send_file_delivers_own_scope_exchange_artifact(_exchange):
    from fleetent.tools.builtin_tools import send_file

    artifact_exchange.register(server_id="gd", rel_path="report.xlsx", scope_key="K1")
    mgr = MagicMock()
    mgr.scope = Scope.SESSION
    with (
        patch("fleetent.tools.builtin_tools._get_manager", return_value=mgr),
        patch(
            "fleetent.outbound.send_file_to",
            AsyncMock(
                return_value=DeliveryReceipt(
                    ok=True, platform="slack", target="x", target_type="user", kind="file"
                )
            ),
        ) as send,
    ):
        result = await send_file(path="/exchange/gd/report.xlsx", tool_context=_ctx("K1"))
    send.assert_called_once()
    # the resolved host file (under the server root) is what gets delivered
    assert str(_exchange / "report.xlsx") == send.call_args.args[3]
    assert "已把文件发送" in result


async def test_send_file_cross_scope_artifact_hard_refused(_exchange):
    from fleetent.tools.builtin_tools import send_file

    # artifact owned by K1; the current run is K2 → cross-scope. send_file has no approval
    # escape, so it must hard-refuse and point to send_im_message, never deliver.
    artifact_exchange.register(server_id="gd", rel_path="report.xlsx", scope_key="K1")
    mgr = MagicMock()
    mgr.scope = Scope.SESSION
    with (
        patch("fleetent.tools.builtin_tools._get_manager", return_value=mgr),
        patch("fleetent.outbound.send_file_to", AsyncMock()) as send,
    ):
        result = await send_file(path="/exchange/gd/report.xlsx", tool_context=_ctx("K2"))
    send.assert_not_called()
    assert "无法发送" in result
    assert "send_im_message" in result


async def test_send_file_exchange_gone_reports_error(_exchange):
    from fleetent.tools.builtin_tools import send_file

    # registered but the underlying file removed → resolve reports "工件已不存在"
    artifact_exchange.register(server_id="gd", rel_path="report.xlsx", scope_key="K1")
    (_exchange / "report.xlsx").unlink()
    mgr = MagicMock()
    mgr.scope = Scope.SESSION
    with (
        patch("fleetent.tools.builtin_tools._get_manager", return_value=mgr),
        patch(
            "fleetent.outbound.send_file_to",
            AsyncMock(
                return_value=DeliveryReceipt(
                    ok=True, platform="slack", target="x", target_type="user", kind="file"
                )
            ),
        ) as send,
    ):
        result = await send_file(path="/exchange/gd/report.xlsx", tool_context=_ctx("K1"))
    send.assert_not_called()
    assert "无法发送" in result
