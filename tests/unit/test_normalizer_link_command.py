"""Agent-side ``/link <code>`` handling in the normalizer (agent-hosted-im, Group 5).

After node exits the IM data plane, the ``/link`` command is handled in the agent inbound
path: the normalizer intercepts it before the agent loop and confirms via the injected
link confirmer (node loopback under managed). Standalone (no confirmer) treats ``/link``
as a normal message (not applicable).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fleetent.im_gateway import access, normalizer
from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext


@pytest.fixture(autouse=True)
def _reset_confirmer():
    access.set_im_link_confirmer(None)
    yield
    access.set_im_link_confirmer(None)


def _link_msg(text: str, reply: AsyncMock, sender_id: str = "U_SENDER") -> NormalizedMessage:
    return NormalizedMessage(
        platform="slack",
        session_id="slack:dm:U:1",
        user_id="U",
        text=text,
        attachments=[],
        reply_func=reply,
        agent_name="support",
        session_context=SessionContext(platform="slack", sender_id=sender_id),
    )


async def test_link_command_managed_confirms_and_replies_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, str]] = []
    access.set_im_link_confirmer(lambda p, puid, code: calls.append((p, puid, code)) or (True, ""))

    # The loop must NOT run for a /link command.
    monkeypatch.setattr("fleetent.runtime.loop.run", AsyncMock(side_effect=AssertionError("loop")))

    reply = AsyncMock()
    await normalizer.route(_link_msg("/link abc123", reply))

    assert calls == [("slack", "U_SENDER", "abc123")]
    assert reply.await_count == 1
    assert "abc" not in reply.await_args.args[0].lower()  # do not echo the code back


async def test_link_command_managed_reports_failure_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access.set_im_link_confirmer(lambda p, puid, code: (False, "Link failed: expired code"))
    monkeypatch.setattr("fleetent.runtime.loop.run", AsyncMock(side_effect=AssertionError("loop")))

    reply = AsyncMock()
    await normalizer.route(_link_msg("/link expired", reply))

    assert reply.await_count == 1
    assert "expired code" in reply.await_args.args[0]


async def test_link_command_missing_sender_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    confirmed: list = []
    access.set_im_link_confirmer(lambda p, puid, code: confirmed.append(1) or (True, ""))
    monkeypatch.setattr("fleetent.runtime.loop.run", AsyncMock(side_effect=AssertionError("loop")))

    reply = AsyncMock()
    await normalizer.route(_link_msg("/link abc123", reply, sender_id=""))

    assert confirmed == []  # cannot confirm without a sender identity
    assert reply.await_count == 1
    assert "sender" in reply.await_args.args[0].lower()


async def test_link_command_standalone_not_intercepted() -> None:
    """No confirmer wired (standalone): /link is not intercepted as a link command.

    confirm_link_available() gates the /link short-circuit, so a standalone runtime treats
    "/link ..." as a normal inbound message rather than a link confirmation.
    """
    assert access.confirm_link_available() is False
    assert access.confirm_link("slack", "U", "abc123") is None
