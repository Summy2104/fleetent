"""Unit tests for resolve_for_runtime fail-fast semantics (agent-hosted-im, D5).

Under the unified agent-hosted model the agent process self-hosts its IM connection, so
a live connector is present in a healthy managed runtime exactly as in standalone. When
managed but no connector is resolvable, resolve_for_runtime must NOT silently return {} —
it logs an error carrying the diagnostic signal so a delivery miss is observable, not silent.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _enable_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "http://127.0.0.1:8790")


def _disable_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_NODE_LOOPBACK_URL", raising=False)


def test_resolve_for_runtime_prefers_live_connector() -> None:
    from fleetent.outbound_connectors import resolve_for_runtime

    live = object()
    assert resolve_for_runtime("support", {"slack": live}) == {"slack": live}


def test_resolve_for_runtime_managed_without_connector_logs_error_not_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fleetent.outbound_connectors as oc

    _enable_managed(monkeypatch)
    fake_logger = MagicMock()
    monkeypatch.setattr(oc, "_logger", fake_logger)

    resolved = oc.resolve_for_runtime("support", {})

    # Still returns {} (no fabricated queue proxy) but the miss is now observable.
    assert resolved == {}
    assert fake_logger.error.call_count == 1
    # The diagnostic carries the agent + managed signal so the miss is traceable.
    assert fake_logger.error.call_args.kwargs.get("agent") == "support"
    assert fake_logger.error.call_args.kwargs.get("managed") is True


def test_resolve_for_runtime_standalone_without_connector_is_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fleetent.outbound_connectors as oc

    _disable_managed(monkeypatch)
    fake_logger = MagicMock()
    monkeypatch.setattr(oc, "_logger", fake_logger)

    resolved = oc.resolve_for_runtime("support", {})

    # Standalone with no connector is a normal non-IM turn — no error noise.
    assert resolved == {}
    assert fake_logger.error.call_count == 0
