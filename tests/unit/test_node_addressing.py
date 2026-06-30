"""Unit tests for the shared platform→node forwarder addressing helper.

Priority: reported forward_host (DB) → FLEETENT_FORWARDER_HOST_OVERRIDE → {node_id}.internal.
This helper is the single source of truth used by both agent_transport (live dial)
and skill backflow bundle capture, so a drifted-skill nomination reaches the node at
its reported address instead of an unresolvable ``{node_id}.internal``.
"""

from __future__ import annotations

import pytest

from fleetent.platform.node_management import node_addressing


@pytest.fixture(autouse=True)
def _clear_override(monkeypatch):
    monkeypatch.delenv("FLEETENT_FORWARDER_HOST_OVERRIDE", raising=False)


def _set_reported(monkeypatch, value):
    monkeypatch.setattr(node_addressing.node_store, "get_forward_host", lambda _nid: value)


def test_prefers_reported_forward_host(monkeypatch) -> None:
    _set_reported(monkeypatch, "10.38.8.143")
    assert node_addressing.resolve_forwarder_base_url("node-x") == "http://10.38.8.143:8767"


def test_falls_back_to_internal_when_no_host_and_no_override(monkeypatch) -> None:
    _set_reported(monkeypatch, None)
    assert node_addressing.resolve_forwarder_base_url("node-x") == "http://node-x.internal:8767"


def test_override_used_when_no_reported_host(monkeypatch) -> None:
    _set_reported(monkeypatch, None)
    monkeypatch.setenv("FLEETENT_FORWARDER_HOST_OVERRIDE", "127.0.0.1")
    assert node_addressing.resolve_forwarder_base_url("node-x") == "http://127.0.0.1:8767"


def test_reported_host_beats_override(monkeypatch) -> None:
    _set_reported(monkeypatch, "10.38.8.143")
    monkeypatch.setenv("FLEETENT_FORWARDER_HOST_OVERRIDE", "127.0.0.1")
    assert node_addressing.resolve_forwarder_base_url("node-x") == "http://10.38.8.143:8767"


@pytest.mark.parametrize(
    "malformed",
    [
        "evil.com/path",
        "node-a@evil.com",
        "10.0.0.5:9999",
        "evil.com#frag",
        "evil.com?x=1",
        "has space",
        "bad_underscore.com",
    ],
)
def test_malformed_reported_host_is_rejected_and_falls_back(monkeypatch, malformed) -> None:
    _set_reported(monkeypatch, malformed)
    assert node_addressing.resolve_forwarder_base_url("node-x") == "http://node-x.internal:8767"


def test_loopback_and_private_reported_hosts_are_allowed(monkeypatch) -> None:
    for host in ("127.0.0.1", "10.38.8.143", "node-a.internal"):
        _set_reported(monkeypatch, host)
        assert node_addressing.resolve_forwarder_base_url("node-x") == f"http://{host}:8767"
