"""Unit tests for platform→node forwarder host resolution priority.

Priority: reported forward_host (DB) → FLEETENT_FORWARDER_HOST_OVERRIDE → {node_id}.internal.
"""

from __future__ import annotations

import pytest

from fleetent.platform.node_management import agent_transport


@pytest.fixture(autouse=True)
def _clear_override(monkeypatch):
    monkeypatch.delenv("FLEETENT_FORWARDER_HOST_OVERRIDE", raising=False)


def _set_reported(monkeypatch, value):
    monkeypatch.setattr(agent_transport.node_store, "get_forward_host", lambda _nid: value)


def test_base_and_ws_prefer_reported_forward_host(monkeypatch) -> None:
    _set_reported(monkeypatch, "10.38.8.143")
    assert agent_transport._forwarder_base_url("node-x") == "http://10.38.8.143:8786"
    assert agent_transport._forwarder_ws_url("node-x") == "ws://10.38.8.143:8786"


def test_falls_back_to_internal_when_no_host_and_no_override(monkeypatch) -> None:
    _set_reported(monkeypatch, None)
    assert agent_transport._forwarder_base_url("node-x") == "http://node-x.internal:8786"
    assert agent_transport._forwarder_ws_url("node-x") == "ws://node-x.internal:8786"


def test_override_used_when_no_reported_host(monkeypatch) -> None:
    _set_reported(monkeypatch, None)
    monkeypatch.setenv("FLEETENT_FORWARDER_HOST_OVERRIDE", "127.0.0.1")
    assert agent_transport._forwarder_base_url("node-x") == "http://127.0.0.1:8786"
    assert agent_transport._forwarder_ws_url("node-x") == "ws://127.0.0.1:8786"


def test_reported_host_beats_override(monkeypatch) -> None:
    _set_reported(monkeypatch, "10.38.8.143")
    monkeypatch.setenv("FLEETENT_FORWARDER_HOST_OVERRIDE", "127.0.0.1")
    assert agent_transport._forwarder_base_url("node-x") == "http://10.38.8.143:8786"


@pytest.mark.parametrize(
    "malformed",
    [
        "evil.com/path",  # path smuggling
        "node-a@evil.com",  # userinfo smuggling
        "10.0.0.5:9999",  # port smuggling
        "evil.com#frag",
        "evil.com?x=1",
        "has space",
        "bad_underscore.com",
    ],
)
def test_malformed_reported_host_is_rejected_and_falls_back(monkeypatch, malformed) -> None:
    # A node-reported host is interpolated into the dial URL; values carrying
    # URL-smuggling characters must be ignored so the platform cannot be steered
    # to a different host (SSRF). Fail safe to the .internal convention.
    _set_reported(monkeypatch, malformed)
    assert agent_transport._forwarder_base_url("node-x") == "http://node-x.internal:8786"
    assert agent_transport._forwarder_ws_url("node-x") == "ws://node-x.internal:8786"


def test_loopback_and_private_reported_hosts_are_allowed(monkeypatch) -> None:
    # Colocated / on-prem nodes legitimately advertise loopback or internal IPs;
    # rejecting these would break single-machine deployments.
    for host in ("127.0.0.1", "10.38.8.143", "node-a.internal"):
        _set_reported(monkeypatch, host)
        assert agent_transport._forwarder_base_url("node-x") == f"http://{host}:8786"
        assert agent_transport._forwarder_ws_url("node-x") == f"ws://{host}:8786"
