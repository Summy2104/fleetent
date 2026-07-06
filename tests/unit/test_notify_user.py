"""Unit tests for notify_user directed-reach (agent-hosted-im, unified path).

Managed agents self-host their IM connection, so notify_user reverse-resolves the user's
IM addresses via the injected agent-side resolver (node loopback) and fans out over the
live process-local connectors — no queue, no node drain. Standalone leaves the resolver
unset → empty addresses → no-op.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def _enable_node_managed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "http://127.0.0.1:8790")


def _disable_node_managed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_NODE_LOOPBACK_URL", raising=False)


def _stub_active_agent(monkeypatch: pytest.MonkeyPatch, name: str = "support") -> None:
    from fleetent import agent_config

    agent = type("A", (), {"name": name})()
    monkeypatch.setattr(agent_config, "active_agent", lambda: agent)


async def test_notify_user_managed_fans_out_over_live_connectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fleetent.outbound as outbound
    from fleetent.im_gateway import access, connector_registry
    from fleetent.outbound_connectors import notify_user

    _enable_node_managed_env(monkeypatch)
    _stub_active_agent(monkeypatch)

    # Injected reverse resolver returns the user's two bound channels.
    monkeypatch.setattr(
        access,
        "resolve_addresses",
        lambda uid: [
            {"platform": "slack", "platform_user_id": "U_SLACK"},
            {"platform": "telegram", "platform_user_id": "123"},
        ],
    )
    slack_conn = object()
    tg_conn = object()
    monkeypatch.setattr(
        connector_registry,
        "snapshot",
        lambda name: {"slack": slack_conn, "telegram": tg_conn},
    )
    send_to = AsyncMock(return_value=None)
    monkeypatch.setattr(outbound, "send_to", send_to)

    await notify_user("user-42", "Please approve this proposal.")

    assert send_to.await_count == 2
    platforms = {call.args[0] for call in send_to.await_args_list}
    assert platforms == {"slack", "telegram"}
    # The resolved platform connector is passed through per channel.
    for call in send_to.await_args_list:
        plat = call.args[0]
        assert call.args[1] is (slack_conn if plat == "slack" else tg_conn)


async def test_notify_user_managed_no_bindings_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fleetent.outbound as outbound
    from fleetent.im_gateway import access
    from fleetent.outbound_connectors import notify_user

    _enable_node_managed_env(monkeypatch)
    _stub_active_agent(monkeypatch)
    monkeypatch.setattr(access, "resolve_addresses", lambda uid: [])
    send_to = AsyncMock()
    monkeypatch.setattr(outbound, "send_to", send_to)

    await notify_user("user-42", "dropped")

    assert send_to.await_count == 0


async def test_notify_user_managed_single_channel_failure_does_not_abort_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fleetent.outbound as outbound
    from fleetent.im_gateway import access, connector_registry
    from fleetent.outbound_connectors import notify_user

    _enable_node_managed_env(monkeypatch)
    _stub_active_agent(monkeypatch)
    monkeypatch.setattr(
        access,
        "resolve_addresses",
        lambda uid: [
            {"platform": "slack", "platform_user_id": "U_SLACK"},
            {"platform": "telegram", "platform_user_id": "123"},
        ],
    )
    monkeypatch.setattr(connector_registry, "snapshot", lambda name: {})

    calls: list[str] = []

    async def _send_to(platform, connector, target, text, **kwargs):
        calls.append(platform)
        if platform == "slack":
            raise RuntimeError("slack boom")
        return None

    monkeypatch.setattr(outbound, "send_to", _send_to)

    # Must not raise even though the first channel throws.
    await notify_user("user-42", "hi")

    assert calls == ["slack", "telegram"]


async def test_notify_user_non_managed_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    import fleetent.outbound as outbound
    from fleetent.im_gateway import access
    from fleetent.outbound_connectors import notify_user

    _disable_node_managed_env(monkeypatch)

    resolve = AsyncMock()
    monkeypatch.setattr(access, "resolve_addresses", resolve)
    send_to = AsyncMock()
    monkeypatch.setattr(outbound, "send_to", send_to)

    await notify_user("user-42", "this should be dropped")

    assert send_to.await_count == 0
    assert resolve.await_count == 0


async def test_notify_user_non_managed_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.outbound_connectors import notify_user

    _disable_node_managed_env(monkeypatch)
    await notify_user("user-42", "test")
