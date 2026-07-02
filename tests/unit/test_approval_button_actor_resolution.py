"""Unit: Slack/Telegram approval button handlers resolve the decision actor before authz.

Guards AAA-8266: the handlers must pass the *resolved* internal user id (managed) — not the
raw platform id — to resolve_approval_request, so the gate's authorized-actor check (which
holds the run principal's internal id) matches. Standalone (no resolver) passes the raw id.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.im_gateway import access
from fleetent.outbound import approval_callback_data


@pytest.fixture(autouse=True)
def _reset_resolver():
    access.set_im_identity_resolver(None)
    yield
    access.set_im_identity_resolver(None)


def _patch_common(monkeypatch):
    """Stub the stores + capture the approver_user_id passed to resolve_approval_request."""
    captured: dict[str, object] = {}

    async def fake_resolve(**kwargs):
        captured["approver_user_id"] = kwargs.get("approver_user_id")
        return True

    monkeypatch.setattr("fleetent.governance.approval_store.get_approval", lambda _id: None)
    monkeypatch.setattr(
        "fleetent.session.manager.get_pending_approval", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "fleetent.governance.approval_router.resolve_approval_request", fake_resolve
    )
    return captured


async def test_slack_button_resolves_actor_managed(monkeypatch):
    from fleetent.im_gateway import slack

    captured = _patch_common(monkeypatch)
    access.set_im_identity_resolver(lambda owner, platform, pid: "uuid-x" if pid == "U123" else pid)

    body = {
        "actions": [{"action_id": "approval_approve", "value": "appr-1"}],
        "user": {"id": "U123"},
        "channel": {"id": "C1"},
        "message": {"ts": "1.1"},
    }
    client = MagicMock()
    client.chat_update = AsyncMock()
    client.chat_postEphemeral = AsyncMock()

    await slack.handle_approval_action(AsyncMock(), body, client, agent_name="bi-intern")
    assert captured["approver_user_id"] == "uuid-x"


async def test_slack_button_passthrough_standalone(monkeypatch):
    from fleetent.im_gateway import slack

    captured = _patch_common(monkeypatch)  # no resolver injected
    body = {
        "actions": [{"action_id": "approval_approve", "value": "appr-1"}],
        "user": {"id": "U123"},
        "channel": {"id": "C1"},
        "message": {"ts": "1.1"},
    }
    client = MagicMock()
    client.chat_update = AsyncMock()
    client.chat_postEphemeral = AsyncMock()

    await slack.handle_approval_action(AsyncMock(), body, client, agent_name="bi-intern")
    assert captured["approver_user_id"] == "U123"


async def test_telegram_button_resolves_actor_managed(monkeypatch):
    from fleetent.im_gateway import telegram

    captured = _patch_common(monkeypatch)
    access.set_im_identity_resolver(lambda owner, platform, pid: "uuid-t" if pid == "123" else pid)

    cq = MagicMock()
    cq.data = approval_callback_data("approve", "appr-1")
    cq.from_user.id = 123
    cq.answer = AsyncMock()
    cq.message.edit_text = AsyncMock()
    update = MagicMock()
    update.callback_query = cq

    await telegram.handle_approval_callback(update, MagicMock(), agent_name="bi-intern")
    assert captured["approver_user_id"] == "uuid-t"
