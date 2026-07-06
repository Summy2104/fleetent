"""Unit tests for directed-reach A4b: reflection user-memory proposal notification.

Covers:
- user-memory proposals call notify_user(proposal.user_id, ...)
- shared-memory and skill proposals still use the original approval-routing path
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent import reflection

# ---------------------------------------------------------------------------
# Task 4.1 — write test (red)
# ---------------------------------------------------------------------------


async def test_notify_pending_proposal_user_memory_calls_notify_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """user-memory domain → notify_user(user_id, message with approval_id)."""
    notify_calls: list[tuple[str, str]] = []

    async def _notify(user_id, msg, **kwargs):
        notify_calls.append((user_id, msg))

    monkeypatch.setattr("fleetent.outbound_connectors.notify_user", _notify)

    # Ensure the existing approval-routing path is NOT called
    gate_notify = AsyncMock()
    monkeypatch.setattr(
        "fleetent.governance.permission_gate.PermissionGate._notify_approvers",
        gate_notify,
    )

    await reflection._notify_pending_proposal(  # noqa: SLF001
        proposal_id="mp-test-123",
        domain="memory",
        action="mark_stale",  # user-memory routing key
        risk="low",
        user_id="user-42",
    )

    assert len(notify_calls) == 1
    called_user_id, called_msg = notify_calls[0]
    assert called_user_id == "user-42"
    assert "mp-test-123" in called_msg  # message contains the proposal id
    gate_notify.assert_not_called()


async def test_notify_pending_proposal_shared_memory_uses_approval_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """shared-memory domain → existing approval-routing path, NOT notify_user."""
    notify_calls: list = []
    monkeypatch.setattr(
        "fleetent.outbound_connectors.notify_user",
        lambda *a, **kw: notify_calls.append(a),
    )

    agent = MagicMock()
    agent.approval = MagicMock()
    monkeypatch.setattr("fleetent.agent_config.active_agent", lambda: agent)
    monkeypatch.setattr(
        "fleetent.agent_config.resolve_approvers",
        lambda *a, **kw: ([], "none"),
    )

    gate_notify = AsyncMock()
    with patch("fleetent.governance.permission_gate.PermissionGate._notify_approvers", gate_notify):
        await reflection._notify_pending_proposal(  # noqa: SLF001
            proposal_id="sp-shared-1",
            domain="memory",
            action="suggest_agent_memory_or_kb",  # agent memory routing key
            risk="low",
            user_id="user-99",
        )

    # notify_user must NOT be called for shared proposals
    assert notify_calls == []


async def test_notify_pending_proposal_skill_uses_approval_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """skill domain → existing approval-routing path, NOT notify_user."""
    notify_calls: list = []
    monkeypatch.setattr(
        "fleetent.outbound_connectors.notify_user",
        lambda *a, **kw: notify_calls.append(a),
    )

    agent = MagicMock()
    agent.approval = MagicMock()
    monkeypatch.setattr("fleetent.agent_config.active_agent", lambda: agent)
    monkeypatch.setattr(
        "fleetent.agent_config.resolve_approvers",
        lambda *a, **kw: ([], "none"),
    )

    gate_notify = AsyncMock()
    with patch("fleetent.governance.permission_gate.PermissionGate._notify_approvers", gate_notify):
        await reflection._notify_pending_proposal(  # noqa: SLF001
            proposal_id="sp-skill-1",
            domain="skill",
            action=None,
            risk="medium",
            user_id=None,
        )

    assert notify_calls == []


async def test_notify_pending_proposal_user_memory_without_user_id_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If user_id is None for user-memory, skip silently (edge: internal call path)."""
    notify_calls: list = []
    monkeypatch.setattr(
        "fleetent.outbound_connectors.notify_user",
        lambda *a, **kw: notify_calls.append(a),
    )

    await reflection._notify_pending_proposal(  # noqa: SLF001
        proposal_id="mp-no-user",
        domain="memory",
        action="mark_stale",
        risk="low",
        user_id=None,
    )

    assert notify_calls == []
