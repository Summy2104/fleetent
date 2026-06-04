"""Unit tests for provider_health: ProviderState + ProviderHealthCache.

Time is always injected via a fake clock; these tests never sleep.
"""

from __future__ import annotations

import fleetent.model.provider_health as ph
from fleetent.model.provider_health import ProviderHealthCache, ProviderState


class FakeClock:
    """Injectable monotonic-style clock; advance() moves time forward."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# ── basic structure (task 2) ──────────────────────────────────────────────────


def test_fresh_cache_reports_available() -> None:
    cache = ProviderHealthCache(failure_threshold=3, cooldown_seconds=60, now=FakeClock())
    assert cache.is_available("model-a") is True


def test_fresh_state_has_zero_failures() -> None:
    state = ProviderState()
    assert state.consecutive_failures == 0
    assert state.unavailable_until == 0.0


def test_constructor_params_injectable() -> None:
    clock = FakeClock()
    cache = ProviderHealthCache(failure_threshold=2, cooldown_seconds=30, now=clock)
    assert cache.failure_threshold == 2
    assert cache.cooldown_seconds == 30


# ── failure threshold → cooldown (task 3) ─────────────────────────────────────


def test_below_threshold_stays_available() -> None:
    cache = ProviderHealthCache(failure_threshold=3, cooldown_seconds=60, now=FakeClock())
    cache.record_failure("m")
    cache.record_failure("m")
    assert cache.is_available("m") is True


def test_reaching_threshold_enters_cooldown() -> None:
    clock = FakeClock()
    cache = ProviderHealthCache(failure_threshold=3, cooldown_seconds=60, now=clock)
    cache.record_failure("m")
    cache.record_failure("m")
    cache.record_failure("m")
    assert cache.is_available("m") is False


def test_cooldown_blocks_within_window() -> None:
    clock = FakeClock()
    cache = ProviderHealthCache(failure_threshold=1, cooldown_seconds=60, now=clock)
    cache.record_failure("m")
    clock.advance(59)
    assert cache.is_available("m") is False


def test_failures_are_per_model() -> None:
    cache = ProviderHealthCache(failure_threshold=1, cooldown_seconds=60, now=FakeClock())
    cache.record_failure("m1")
    assert cache.is_available("m1") is False
    assert cache.is_available("m2") is True


# ── half-open + recovery (task 4) ─────────────────────────────────────────────


def test_cooldown_expiry_allows_half_open() -> None:
    clock = FakeClock()
    cache = ProviderHealthCache(failure_threshold=1, cooldown_seconds=60, now=clock)
    cache.record_failure("m")
    clock.advance(60)
    assert cache.is_available("m") is True


def test_half_open_failure_reenters_cooldown() -> None:
    clock = FakeClock()
    cache = ProviderHealthCache(failure_threshold=1, cooldown_seconds=60, now=clock)
    cache.record_failure("m")
    clock.advance(60)
    assert cache.is_available("m") is True  # half-open
    cache.record_failure("m")
    assert cache.is_available("m") is False  # back in cooldown


def test_success_resets_failure_count() -> None:
    clock = FakeClock()
    cache = ProviderHealthCache(failure_threshold=3, cooldown_seconds=60, now=clock)
    cache.record_failure("m")
    cache.record_failure("m")
    cache.record_success("m")
    cache.record_failure("m")
    cache.record_failure("m")
    # Only 2 failures since the success; threshold (3) not reached.
    assert cache.is_available("m") is True


def test_success_clears_cooldown() -> None:
    clock = FakeClock()
    cache = ProviderHealthCache(failure_threshold=1, cooldown_seconds=60, now=clock)
    cache.record_failure("m")
    assert cache.is_available("m") is False
    cache.record_success("m")
    assert cache.is_available("m") is True


# ── config injection (task 5) ─────────────────────────────────────────────────


def test_default_config_reads_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        ph, "_default_config", lambda: {"failure_threshold": 7, "cooldown_seconds": 99}
    )
    cache = ProviderHealthCache()
    assert cache.failure_threshold == 7
    assert cache.cooldown_seconds == 99


def test_constructor_param_overrides_config(monkeypatch) -> None:
    monkeypatch.setattr(
        ph, "_default_config", lambda: {"failure_threshold": 7, "cooldown_seconds": 99}
    )
    cache = ProviderHealthCache(failure_threshold=2)
    assert cache.failure_threshold == 2
    assert cache.cooldown_seconds == 99  # falls through to config


# ── replaceable module singleton (task 6) ─────────────────────────────────────


def test_module_singleton_is_replaceable(monkeypatch) -> None:
    replacement = ProviderHealthCache(failure_threshold=1, cooldown_seconds=60, now=FakeClock())
    monkeypatch.setattr(ph, "_cache", replacement)
    assert ph.get_health_cache() is replacement


def test_get_health_cache_returns_cache() -> None:
    assert isinstance(ph.get_health_cache(), ProviderHealthCache)
