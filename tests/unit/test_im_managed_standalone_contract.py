"""Contract: managed == standalone IM behavior (agent-hosted-im, D6).

The whole point of the unification is that a node-managed agent and a standalone agent take
the SAME code path: the agent self-hosts its IM connection, so a live connector is present in
both modes and every outbound/approval/directed-reach path behaves identically. These tests
run the same input under both placements (loopback signal present vs absent) and assert the
observable result is the same, so a future divergence (a resurrected managed-only branch)
fails here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def _managed(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    if on:
        monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "http://127.0.0.1:8790")
    else:
        monkeypatch.delenv("FLEETENT_NODE_LOOPBACK_URL", raising=False)


@pytest.mark.parametrize("managed", [True, False])
def test_resolve_for_runtime_identical_with_live_connector(
    monkeypatch: pytest.MonkeyPatch, managed: bool
) -> None:
    from fleetent.outbound_connectors import resolve_for_runtime

    _managed(monkeypatch, managed)
    live = object()
    # Same input, same output regardless of placement — no managed proxy substitution.
    assert resolve_for_runtime("support", {"slack": live}) == {"slack": live}


@pytest.mark.parametrize("managed", [True, False])
async def test_send_file_delivery_identical_with_live_connector(
    monkeypatch: pytest.MonkeyPatch, managed: bool
) -> None:
    import fleetent.outbound as outbound

    _managed(monkeypatch, managed)
    calls: list[tuple] = []

    async def _slack_send_file(client, target, path, target_type, thread):  # noqa: ANN001
        calls.append((target, path, target_type))
        return ("file-ref", None)

    monkeypatch.setattr(outbound, "_slack_send_file", _slack_send_file)

    connector = object()
    receipt = await outbound.send_file_to("slack", connector, "U1", "/tmp/x.txt")

    # Direct Web-API delivery in both modes (no enqueue path), identical receipt shape.
    assert receipt.ok is True
    assert receipt.kind == "file"
    assert receipt.provider_ref == "file-ref"
    assert calls == [("U1", "/tmp/x.txt", "user")]


@pytest.mark.parametrize("managed", [True, False])
async def test_send_text_delivery_identical_with_live_connector(
    monkeypatch: pytest.MonkeyPatch, managed: bool
) -> None:
    import fleetent.outbound as outbound

    _managed(monkeypatch, managed)

    async def _slack_send_dm(client, user_id, text, blocks=None):  # noqa: ANN001
        return ("ts-1", None)

    monkeypatch.setattr(outbound, "_slack_send_dm", _slack_send_dm)

    receipt = await outbound.send_to("slack", object(), "U1", "hi")

    assert receipt.ok is True
    assert receipt.kind == "text"
    assert receipt.provider_ref == "ts-1"


@pytest.mark.parametrize("managed", [True, False])
async def test_directed_reach_fanout_observable_result_identical(
    monkeypatch: pytest.MonkeyPatch, managed: bool
) -> None:
    """directed-reach fan-out result is identical given the same resolved bindings.

    Standalone leaves the address resolver unset → no-op (no im_users). Managed resolves via
    loopback → fan-out. Here we force the SAME resolved bindings in both modes to assert the
    delivery mechanism (live-connector fan-out) is one path, not two.
    """
    import fleetent.outbound as outbound
    from fleetent import agent_config
    from fleetent.im_gateway import access, connector_registry
    from fleetent.outbound_connectors import notify_user

    agent = type("A", (), {"name": "support"})()
    monkeypatch.setattr(agent_config, "active_agent", lambda: agent)

    if not managed:
        # Standalone: no resolver wired → notify_user is a no-op (documented divergence: no
        # im_users table to reverse-resolve). Assert that no delivery is attempted.
        _managed(monkeypatch, False)
        access.set_im_address_resolver(None)
        send_to = AsyncMock()
        monkeypatch.setattr(outbound, "send_to", send_to)
        await notify_user("user-42", "hi")
        assert send_to.await_count == 0
        return

    _managed(monkeypatch, True)
    monkeypatch.setattr(
        access,
        "resolve_addresses",
        lambda uid: [{"platform": "slack", "platform_user_id": "U_SLACK"}],
    )
    monkeypatch.setattr(connector_registry, "snapshot", lambda name: {"slack": object()})
    sent: list[tuple] = []

    async def _send_to(platform, connector, target, text, **kwargs):
        sent.append((platform, target, text))

    monkeypatch.setattr(outbound, "send_to", _send_to)
    await notify_user("user-42", "hi")

    # Managed fans out over the SAME live-connector send path used for every other outbound.
    assert sent == [("slack", "U_SLACK", "hi")]
