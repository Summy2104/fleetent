"""Passive provider health cache: a per-model circuit breaker for fallback.

`_call_with_fallback` / `_stream_with_fallback` feed real call outcomes here:
a provider that fails (rate-limit / unavailable, per error classification) a
configured number of times in a row is marked temporarily unavailable so the
fallback loop skips it instead of paying its timeout on every request. After the
cooldown elapses the provider is half-opened (allowed one probe); a success
restores it, another failure re-arms the cooldown.

No global mutable state is exposed bare: state lives inside an injectable
`ProviderHealthCache`, time comes from an injectable `now` (default
`time.monotonic`), and the module singleton is reached through a getter that
tests monkeypatch — mirroring `session_mgr` / `permission_gate`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

HealthConfig = dict[str, int]


def _default_config() -> HealthConfig:
    """Deployment-level defaults from the active agent config. Lazy import
    mirrors context_mgr / termination to keep this module import-light."""
    from fleetent import agent_config

    s = agent_config.active_agent_or_default()
    return {
        "failure_threshold": s.provider_failure_threshold,
        "cooldown_seconds": s.provider_cooldown_seconds,
    }


@dataclass
class ProviderState:
    """Per-model breaker state.

    `unavailable_until` is a `now()`-domain timestamp; 0 means available (closed).
    A positive value in the future means open (cooling down); once `now()` reaches
    it the breaker is half-open and `is_available` lets one probe through.
    """

    consecutive_failures: int = 0
    unavailable_until: float = 0.0


@dataclass
class ProviderHealthCache:
    """Injectable per-model circuit breaker. Tolerates benign concurrent races
    (counts are plain int increments; breaker semantics are insensitive to the
    occasional off-by-one) — no lock by design."""

    failure_threshold: int | None = None
    cooldown_seconds: int | None = None
    now: Callable[[], float] = time.monotonic
    _states: dict[str, ProviderState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Precedence: constructor param > Settings (env) > pydantic field default.
        # Resolve config lazily only when a knob was left None.
        if self.failure_threshold is None or self.cooldown_seconds is None:
            cfg = _default_config()
            if self.failure_threshold is None:
                self.failure_threshold = cfg["failure_threshold"]
            if self.cooldown_seconds is None:
                self.cooldown_seconds = cfg["cooldown_seconds"]

    def _state(self, model: str) -> ProviderState:
        st = self._states.get(model)
        if st is None:
            st = ProviderState()
            self._states[model] = st
        return st

    def is_available(self, model: str) -> bool:
        """True when the breaker is closed or half-open (cooldown elapsed)."""
        st = self._states.get(model)
        if st is None or st.unavailable_until == 0.0:
            return True
        return self.now() >= st.unavailable_until

    def record_failure(self, model: str) -> None:
        """Count a switchable failure; arm the cooldown on reaching the threshold."""
        st = self._state(model)
        st.consecutive_failures += 1
        assert self.failure_threshold is not None  # set in __post_init__
        if st.consecutive_failures >= self.failure_threshold:
            assert self.cooldown_seconds is not None  # set in __post_init__
            st.unavailable_until = self.now() + self.cooldown_seconds

    def record_success(self, model: str) -> None:
        """Close the breaker: reset the failure count and clear any cooldown."""
        st = self._state(model)
        st.consecutive_failures = 0
        st.unavailable_until = 0.0


# Module-level replaceable singleton, reached only through get_health_cache() so
# tests can monkeypatch `_cache`. Lazily built on first use to keep importing
# this module side-effect-free (Settings is read only when the cache is needed).
_cache: ProviderHealthCache | None = None


def get_health_cache() -> ProviderHealthCache:
    """Return the process-wide health cache (replaceable for test isolation)."""
    global _cache
    if _cache is None:
        _cache = ProviderHealthCache()
    return _cache
