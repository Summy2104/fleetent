"""Integration: equivalence replay of the 2026-06-12 my-bot incident (§8.4).

Incident: a google-drive MCP export landed in the server's private dir, send_file's fence
couldn't reach it → the model couldn't deliver and faked completion. This replays the fixed
chain at the persistence/assembly level (real sqlite, mock connector/docker): MCP result
path → deterministic rewrite + ledger registration → send_file resolves /exchange one-step.
The live replay (real Slack + google-workspace-mcp) is left to a docker/live environment.
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
    # google-workspace-mcp's effective root (its export landed here in the incident).
    root = tmp_path / "exchange" / "google-drive" / "data"
    root.mkdir(parents=True)
    artifact_exchange.register_server_root("google-drive", root)
    return root


async def test_incident_export_then_send_file_one_step(_exchange):
    """google-drive exports an xlsx → rewrite+register → send_file delivers it in one call."""
    from fleetent.tools.builtin_tools import send_file

    root = _exchange
    # 1) The MCP tool wrote the export and its result text names the host path.
    (root / "reports" / "q3.xlsx").parent.mkdir(parents=True, exist_ok=True)
    (root / "reports" / "q3.xlsx").write_bytes(b"xlsx-bytes")
    mcp_result = f'{{"status": "ok", "localPath": "{root}/reports/q3.xlsx"}}'

    # 2) The chokepoint rewrite turns the host path into /exchange/... and registers it,
    #    attributed to the run's scope_key (the DM session).
    rewritten = artifact_exchange.rewrite_and_register(
        "google-drive", mcp_result, scope_key="slack:dm:U1:ts", session_id="slack:dm:U1:ts"
    )
    assert "/exchange/google-drive/reports/q3.xlsx" in rewritten

    # 3) The model calls send_file with that /exchange path — one step, no manual rebuild.
    sc = types.SimpleNamespace(platform="slack", sender_id="U1", chat_type="dm")
    ctx = ToolContext(
        session_id="slack:dm:U1:ts",
        scope_key="slack:dm:U1:ts",
        session_context=sc,
        outbound_connectors={"slack": object()},
    )
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
        result = await send_file(path="/exchange/google-drive/reports/q3.xlsx", tool_context=ctx)

    # The real exported host file is delivered to the DM sender — no faked completion.
    send.assert_called_once()
    assert str(root / "reports" / "q3.xlsx") == send.call_args.args[3]
    assert "已把文件发送" in result


@pytest.mark.skipif(True, reason="live replay needs real Slack + google-workspace-mcp + docker")
async def test_incident_live_replay_placeholder():  # pragma: no cover
    """Reserved for the real-environment replay (out of scope for the mock suite)."""
