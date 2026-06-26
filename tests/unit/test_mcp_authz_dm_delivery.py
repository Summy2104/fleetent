"""Unit tests for Group 6.3: authorization-link delivery is a private DM, never a channel.

``outbound.make_mcp_authz_deliverer`` builds a per-call deliverer that DMs the requesting
user (sender) their authorization link, even when the triggering call arrived in a channel,
so no other channel member can intercept the one-shot ``state``. The connector's send is
stubbed and the target/target_type asserted.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fleetent.outbound import DeliveryReceipt, make_mcp_authz_deliverer


class _RecordingConnector:
    """Stand-in IM connector capturing send_to arguments."""


@pytest.fixture
def _patch_send(monkeypatch):
    sent: list[dict] = []

    async def _fake_send_to(platform, connector, target, text, *, target_type="user", **kw):
        sent.append(
            {"platform": platform, "target": target, "text": text, "target_type": target_type}
        )
        return DeliveryReceipt(
            ok=True, platform=platform, target=target, target_type=target_type, kind="text"
        )

    import fleetent.outbound as ob

    monkeypatch.setattr(ob, "send_to", _fake_send_to)
    return sent


def _ctx(*, chat_type: str, sender_id: str = "U123", platform: str = "slack"):
    connector = _RecordingConnector()
    session_context = SimpleNamespace(platform=platform, sender_id=sender_id, chat_type=chat_type)
    return SimpleNamespace(
        outbound_connectors={platform: connector},
        session_context=session_context,
        conversation_address=None,
    )


async def test_deliver_dms_sender_in_channel_context(_patch_send):
    """Even when the call came from a channel, the link DMs the sender (target_type=user)."""
    deliverer = make_mcp_authz_deliverer(_ctx(chat_type="channel", sender_id="U123"))
    assert deliverer is not None
    ok = await deliverer("U123", "ag1", "srv", "https://as.internal/authorize?state=abc")
    assert ok is True
    assert len(_patch_send) == 1
    sent = _patch_send[0]
    assert sent["target_type"] == "user"  # DM, never a channel post
    assert sent["target"] == "U123"  # the sender themselves
    assert "https://as.internal/authorize?state=abc" in sent["text"]


async def test_deliver_dms_sender_in_dm_context(_patch_send):
    deliverer = make_mcp_authz_deliverer(_ctx(chat_type="dm", sender_id="U999"))
    assert deliverer is not None
    await deliverer("U999", "ag1", "srv", "https://as/x")
    assert _patch_send[0]["target_type"] == "user"
    assert _patch_send[0]["target"] == "U999"


def test_no_deliverer_without_connector():
    ctx = SimpleNamespace(
        outbound_connectors={},
        session_context=SimpleNamespace(platform="slack", sender_id="U1", chat_type="dm"),
        conversation_address=None,
    )
    assert make_mcp_authz_deliverer(ctx) is None


def test_no_deliverer_without_sender():
    ctx = SimpleNamespace(
        outbound_connectors={"slack": _RecordingConnector()},
        session_context=SimpleNamespace(platform="slack", sender_id="", chat_type="dm"),
        conversation_address=None,
    )
    assert make_mcp_authz_deliverer(ctx) is None
