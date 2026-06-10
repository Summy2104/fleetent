"""Integration tests for approval endpoints on standalone agent_app.

Standalone agent (fleetent agent run) must expose GET /approvals and
POST /approvals/{id}/resolve so medium/high-risk tool calls can be
approved without requiring the full platform server.
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from fleetent import user_store
from fleetent.governance import approval_store
from fleetent.governance.permission_gate import PermissionGate
from fleetent.runtime import agent_app


def _make_client(monkeypatch, tmp_path):
    fake_user = MagicMock(spec=user_store.User)
    fake_user.id = "U1"
    monkeypatch.setattr(user_store, "authenticate", lambda _token: (fake_user, {}))
    # approval_store.DB_PATH freezes at import from the ambient FLEETENT_HOME; pin it
    # to tmp so the endpoints never touch a real (possibly legacy-schema) home DB.
    monkeypatch.setattr(approval_store, "DB_PATH", tmp_path / "agent.db")
    app = agent_app.build_app("test-agent")
    return TestClient(app, raise_server_exceptions=True)


def test_get_approvals_endpoint_exists(monkeypatch, tmp_path):
    """GET /approvals returns a list (not 404)."""
    client = _make_client(monkeypatch, tmp_path)
    resp = client.get("/approvals")
    assert resp.status_code == 200, (
        f"GET /approvals returned {resp.status_code}; endpoint must exist on standalone agent"
    )
    assert isinstance(resp.json(), list)


def test_resolve_approval_unknown_id_returns_404(monkeypatch, tmp_path):
    """POST /approvals/{id}/resolve with unknown id returns 404."""
    client = _make_client(monkeypatch, tmp_path)
    resp = client.post(
        "/approvals/nonexistent/resolve",
        json={"decision": "approved", "approver_user_id": "test"},
    )
    assert resp.status_code == 404, f"Expected 404 for unknown approval, got {resp.status_code}"


async def test_resolve_approval_happy_path(monkeypatch, tmp_path):
    """POST /approvals/{id}/resolve with known pending id resolves it."""
    import asyncio

    from fleetent.governance import permission_gate as pg

    # Isolate the agent-side approval store BEFORE the background request_approval
    # writes its pending row (DB_PATH freezes at import from the ambient home).
    monkeypatch.setattr(approval_store, "DB_PATH", tmp_path / "agent.db")
    # Install a fresh gate with short timeouts so the test doesn't hang
    gate = PermissionGate(medium_timeout=5.0, high_timeout=5.0)
    monkeypatch.setattr(pg, "_default_gate", gate)

    # Register an approval in the background
    async def noop(_msg: str) -> None:
        pass

    # R1 default-closed: with no reachable approver the request is rejected
    # immediately, so a pending approval requires routing + a mocked outbound DM.
    from unittest.mock import AsyncMock

    import fleetent.outbound as outbound_mod
    from fleetent.agent_config import ApprovalRouting

    monkeypatch.setattr(outbound_mod, "send_to", AsyncMock(return_value=True))
    monkeypatch.setattr(outbound_mod, "is_reachable", AsyncMock(return_value=True))
    routing = ApprovalRouting(by_risk={"medium": {"approvers": ["slack:U_LEAD"], "policy": "any"}})

    approval_id = uuid.uuid4().hex[:12]
    task = asyncio.create_task(
        gate.request_approval(
            approval_id=approval_id,
            risk_level="medium",
            tool_name="run_code",
            tool_args={"code": "x=1"},
            requester_user_id="U1",
            reply_func=noop,
            approval_routing=routing,
            outbound_connectors={"slack": AsyncMock()},
        )
    )
    # yield to let the task register the event
    await asyncio.sleep(0)

    client = _make_client(monkeypatch, tmp_path)
    resp = client.post(
        f"/approvals/{approval_id}/resolve",
        json={"decision": "approved", "approver_user_id": "test"},
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "approved"

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
