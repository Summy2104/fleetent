"""Unit tests for the single managed-runtime placement signal (agent-hosted-im)."""

import pytest

from fleetent import runtime_placement


def test_is_managed_true_only_with_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "http://127.0.0.1:8790")
    assert runtime_placement.is_managed() is True


def test_is_managed_false_without_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_NODE_LOOPBACK_URL", raising=False)
    assert runtime_placement.is_managed() is False


def test_three_var_signal_alone_is_not_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deprecated NODE_ID/PLATFORM_URL/SERVICE_KEY trio must NOT imply managed —
    it was never delivered to container agent .env (AAA-8208 root cause)."""
    monkeypatch.delenv("FLEETENT_NODE_LOOPBACK_URL", raising=False)
    monkeypatch.setenv("FLEETENT_NODE_ID", "node-a")
    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", "https://platform.internal")
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-" + "1" * 64)
    assert runtime_placement.is_managed() is False


def test_blank_loopback_is_not_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "   ")
    assert runtime_placement.is_managed() is False


def test_is_node_managed_runtime_delegates_to_is_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    """outbound_connectors.is_node_managed_runtime converges onto the single signal."""
    from fleetent import outbound_connectors

    monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "http://127.0.0.1:8790")
    assert outbound_connectors.is_node_managed_runtime() is True
    monkeypatch.delenv("FLEETENT_NODE_LOOPBACK_URL", raising=False)
    assert outbound_connectors.is_node_managed_runtime() is False
