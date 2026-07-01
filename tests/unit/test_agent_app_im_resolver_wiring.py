"""boot-time injection of agent-side IM identity/address resolvers (agent-hosted-im)."""

import pytest

from fleetent.im_gateway import access
from fleetent.runtime import agent_app


@pytest.fixture(autouse=True)
def _reset_resolvers():
    access.set_im_identity_resolver(None)
    access.set_im_address_resolver(None)
    yield
    access.set_im_identity_resolver(None)
    access.set_im_address_resolver(None)


def test_managed_wires_both_resolvers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "http://127.0.0.1:8790")
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-agent-token")

    agent_app._wire_managed_im_resolvers("support", "acme")

    assert isinstance(access._im_identity_resolver, access.AgentIdentityResolver)
    assert isinstance(access._im_address_resolver, access.AgentAddressResolver)


def test_standalone_leaves_resolvers_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_NODE_LOOPBACK_URL", raising=False)
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-agent-token")

    agent_app._wire_managed_im_resolvers("support", "acme")

    assert access._im_identity_resolver is None
    assert access._im_address_resolver is None
