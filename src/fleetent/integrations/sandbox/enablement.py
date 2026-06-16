"""Code-execution enablement decision (per-agent-sandbox-enablement).

Whether the `run_code` tool is exposed to a given agent is decided by two gates that
collapse into one judgement here:

1. Runtime capability — `Mode.ON` when the selected sandbox backend is available,
   `Mode.OFF` when it is not (no Docker / msb unreachable). Derived purely from a
   backend probe; there is no global tri-state `mode` and nothing is read from
   `platform.yaml`.
2. Per-agent `features.code_execution` — the sole policy input. `None`/`True` enable,
   explicit `False` disables (preserving the legacy `all` default).

The functions are side-effect free so the schema-filter point (agent_loop) only reads
them.
"""

from __future__ import annotations

from enum import StrEnum

from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.enablement")


class Mode(StrEnum):
    OFF = "off"  # backend unavailable → no agent can run code
    ON = "on"  # backend available → per-agent code_execution governs


# Process-level cache of the resolved effective mode for non-server callers (IM
# gateway / CLI) that lack the server's app.state. The first call probes the backend
# once per process; later calls reuse it (D2: startup-once intent). Injectable
# single-value cache (monkeypatched to None in tests) — the only mutable module state.
_effective_mode_cache: Mode | None = None


async def get_effective_mode(backend: object | None = None) -> Mode:
    """Return the effective sandbox capability (ON/OFF), caching the backend probe.

    `Mode.ON` when the selected backend's `available()` probe succeeds, else `Mode.OFF`
    (D2 degrade: no Docker / msb unreachable disables code execution for every agent).
    `backend` is the configured backend to probe; when omitted it is resolved via the
    factory. The first call seeds the process cache so later loop/IM calls reuse it. No
    `platform.yaml` is read.
    """
    global _effective_mode_cache
    if _effective_mode_cache is not None:
        return _effective_mode_cache
    if backend is None:
        from fleetent.integrations.sandbox.factory import create_backend

        backend = create_backend()
    available = await backend.available()  # type: ignore[attr-defined]
    _effective_mode_cache = Mode.ON if available else Mode.OFF
    return _effective_mode_cache


def is_code_execution_enabled(mode: Mode, code_execution: bool | None) -> bool:
    """Decide whether `run_code` is enabled for an agent.

    - OFF (no runtime sandbox capability): always disabled (fail-closed).
    - ON: enabled unless the agent explicitly opts out (`False`); `None`/`True` on
      (preserves the legacy `all`-mode default).
    """
    if mode is Mode.OFF:
        return False
    return code_execution is not False
