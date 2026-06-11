"""Unit tests: permission gate auto-approve on allow-always hit (approval-minimization)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.governance import approval_allowlist_store as allowlist
from fleetent.governance import approval_store
from fleetent.governance.permission_gate import PermissionGate


@pytest.fixture(autouse=True)
def _mock_store(monkeypatch):
    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())


async def test_allowlisted_fingerprint_auto_approves_without_notifying(monkeypatch):
    monkeypatch.setattr(allowlist, "is_allowed", lambda fp, **kw: True)
    gate = PermissionGate(medium_timeout=0.1, high_timeout=0.1)
    notify = AsyncMock(return_value=["slack:U_LEAD"])
    monkeypatch.setattr(gate, "_notify_approvers", notify)
    reply = AsyncMock()

    decision = await gate.request_approval(
        approval_id="a1",
        risk_level="high",
        tool_name="run_code",
        tool_args={"code": "ls"},
        requester_user_id="user:alice",
        reply_func=reply,
    )

    assert decision == "approved"
    notify.assert_not_called()


async def test_allowlisted_writes_auto_approved_audit(monkeypatch):
    monkeypatch.setattr(allowlist, "is_allowed", lambda fp, **kw: True)
    update = MagicMock()
    monkeypatch.setattr(approval_store, "update_approval", update)
    gate = PermissionGate(medium_timeout=0.1, high_timeout=0.1)
    monkeypatch.setattr(gate, "_notify_approvers", AsyncMock(return_value=[]))

    await gate.request_approval(
        approval_id="a2",
        risk_level="high",
        tool_name="run_code",
        tool_args={"code": "ls"},
        requester_user_id="user:alice",
        reply_func=AsyncMock(),
    )

    assert update.called
    # the audit row records the auto-approval
    statuses = [c.kwargs.get("status") for c in update.call_args_list]
    assert "auto_approved" in statuses


async def test_non_allowlisted_goes_through_notify(monkeypatch):
    monkeypatch.setattr(allowlist, "is_allowed", lambda fp, **kw: False)
    gate = PermissionGate(medium_timeout=0.1, high_timeout=0.1)
    notify = AsyncMock(return_value=[])  # no approver -> default-closed reject
    monkeypatch.setattr(gate, "_notify_approvers", notify)

    decision = await gate.request_approval(
        approval_id="a3",
        risk_level="high",
        tool_name="run_code",
        tool_args={"code": "ls"},
        requester_user_id="user:alice",
        reply_func=AsyncMock(),
    )

    notify.assert_called_once()
    assert decision == "rejected"


# ── resolve(always=True) persists the grant (task 3) ──────────────────────────


async def _gate_with_pending(monkeypatch, fp: str):
    gate = PermissionGate(medium_timeout=0.1, high_timeout=0.1)
    # Suspend model: a pending approval is tracked in the _pending registry (no Event).
    gate._pending.add("a1")
    gate._pending_fp["a1"] = (fp, "user:alice", "run_code")
    return gate


async def test_resolve_always_persists_grant(monkeypatch):
    add = MagicMock()
    monkeypatch.setattr(allowlist, "add_grant", add)
    fp = allowlist.fingerprint("user:alice", "run_code", {"code": "ls"})
    gate = await _gate_with_pending(monkeypatch, fp)

    ok = await gate.resolve("a1", "approved", "slack:U_LEAD", always=True)
    assert ok is True
    assert add.called
    assert add.call_args.kwargs["fingerprint"] == fp
    assert add.call_args.kwargs["created_by"] == "slack:U_LEAD"


async def test_resolve_without_always_does_not_persist(monkeypatch):
    add = MagicMock()
    monkeypatch.setattr(allowlist, "add_grant", add)
    fp = allowlist.fingerprint("user:alice", "run_code", {"code": "ls"})
    gate = await _gate_with_pending(monkeypatch, fp)

    await gate.resolve("a1", "approved", "slack:U_LEAD", always=False)
    add.assert_not_called()


async def test_resolve_reject_always_does_not_persist(monkeypatch):
    add = MagicMock()
    monkeypatch.setattr(allowlist, "add_grant", add)
    fp = allowlist.fingerprint("user:alice", "run_code", {"code": "ls"})
    gate = await _gate_with_pending(monkeypatch, fp)

    await gate.resolve("a1", "rejected", "slack:U_LEAD", always=True)
    add.assert_not_called()
