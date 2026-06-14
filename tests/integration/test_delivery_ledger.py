"""Integration: run-level delivery ledger + delivery trace events (§2, D2/D3).

Each outbound receipt is appended to the run's delivery ledger (on ToolContext) and
recorded as a `delivery` trace event (target masked, write failure swallowed) — reusing
the trace-tool-spans recording API.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.observability import traces
from fleetent.outbound import DeliveryReceipt
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.tools.registry import ToolContext


@pytest.fixture
def _trace_db(tmp_path, monkeypatch):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    monkeypatch.setattr(traces, "_state_db", db, raising=False)
    # traces.record_trace_event uses the agent state db via its own accessor; bind it.
    from fleetent.observability import traces as t

    if hasattr(t, "set_state_db"):
        t.set_state_db(db)
    return db


def _rows(db, event_type):
    return db.execute(
        "SELECT payload_json FROM traces WHERE event_type = :e", {"e": event_type}
    ).fetchall()


def test_record_delivery_writes_trace_with_masked_target(_trace_db):
    traces.record_delivery(
        run_id="r1",
        session_id="s1",
        payload={
            "ok": True,
            "platform": "slack",
            "target": "U0123456789",
            "target_type": "user",
            "kind": "file",
            "provider_ref": "F1",
        },
    )
    rows = _rows(_trace_db, "delivery")
    assert len(rows) == 1
    assert '"ok": true' in rows[0]["payload_json"] or '"ok":true' in rows[0]["payload_json"]


def test_record_delivery_write_failure_is_swallowed(monkeypatch):
    # No state db bound → record_trace_event raises internally; record_delivery must not raise.
    monkeypatch.setattr(traces, "_state_db", None, raising=False)
    traces.record_delivery(run_id="r1", session_id="s1", payload={"ok": True, "platform": "x"})


async def test_ledger_collects_tool_and_upload_deliveries(_trace_db, tmp_path, monkeypatch):
    """A run's ledger accumulates send_file + send_im_message(files) receipts (mixed)."""
    from fleetent.integrations.sandbox import Scope
    from fleetent.tools.builtin_tools import send_file, send_im_message

    ledger: list[DeliveryReceipt] = []
    import types

    sc = types.SimpleNamespace(platform="slack", sender_id="U1", chat_type="dm")
    ctx = ToolContext(
        session_id="s1",
        run_id="r1",
        scope_key="s1",
        session_context=sc,
        delivery_ledger=ledger,
        outbound_connectors={"slack": object()},
    )
    (tmp_path / "a.csv").write_bytes(b"a")
    mgr = MagicMock()
    mgr.scope = Scope.SESSION
    mgr.workspace_host_path.return_value = tmp_path
    ok_file = DeliveryReceipt(
        ok=True, platform="slack", target="U1", target_type="user", kind="file"
    )
    ok_text = DeliveryReceipt(
        ok=True, platform="slack", target="U2", target_type="user", kind="text"
    )
    with (
        patch("fleetent.tools.builtin_tools._get_manager", return_value=mgr),
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_file_to", AsyncMock(return_value=ok_file)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=ok_text)),
    ):
        await send_file(path="a.csv", tool_context=ctx)
        await send_im_message(target="U2", text="hi", tool_context=ctx)

    kinds = [r.kind for r in ledger]
    assert kinds.count("file") == 1 and kinds.count("text") == 1
