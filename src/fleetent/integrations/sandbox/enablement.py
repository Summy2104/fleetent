"""Three-state code-execution enablement decision (SB3).

Pure decision logic for whether the `run_code` tool is exposed to a given agent.
Two gates collapse into one judgement here: the global `mode` (off/selective/all)
and the agent-level `features.code_execution` switch. Docker-unavailable degrades
the effective mode to OFF at startup (`resolve_effective_mode`). The functions are
side-effect free so the schema-filter point (agent_loop) only reads them.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml

from fleetent import paths
from fleetent.observability.structured_logging import get_logger

_logger = get_logger("sandbox.enablement")

# platform.yaml is the home of the shared `sandbox:` section (SB3 owns the
# skeleton; SB2 adds scope/idle_hours, SB4 adds resources). Injectable module-level
# constant (no global mutable state) so tests monkeypatch it to an isolated path.
SETTINGS_PATH: Path = paths.platform_yaml_path()

_DEFAULT_MODE_NAME = "all"


class Mode(StrEnum):
    OFF = "off"
    SELECTIVE = "selective"
    ALL = "all"


def load_sandbox_mode() -> Mode:
    """Read the configured sandbox mode from `platform.yaml`'s sandbox section.

    Returns `Mode.ALL` when the file, the `sandbox:` section, or `mode` is absent or
    invalid (logging a warning on an unrecognised value), keeping the documented
    default ("all") and never failing startup. YAML parses a bare `off` as the
    boolean False, so that case is mapped back to the OFF mode name.
    """
    raw_mode = _read_raw_mode()
    if raw_mode is None:
        return Mode.ALL
    if raw_mode is False:
        return Mode.OFF
    if raw_mode is True:
        return Mode.ALL
    try:
        return Mode(str(raw_mode))
    except ValueError:
        _logger.warn("sandbox_mode_invalid", value=repr(raw_mode), falling_back_to=Mode.ALL.value)
        return Mode.ALL


# Process-level cache of the resolved effective mode for non-server callers (IM
# gateway / CLI) that lack the server's app.state. The server resolves and stores
# its own value in lifespan; this cache exists so those other entry points probe
# Docker once per process rather than per message (D2: startup-once intent). It is
# a deliberate, injectable single-value cache (monkeypatched to None in tests) —
# the only mutable module state here, mirroring model_router's file cache.
_effective_mode_cache: Mode | None = None


async def get_effective_mode() -> Mode:
    """Return the effective sandbox mode for non-server callers, caching the probe.

    Resolves `load_sandbox_mode()` against a one-time Docker availability probe and
    memoises the result for the process. The server path does not use this (it
    resolves into app.state at startup); this serves IM gateway / CLI callers.
    """
    global _effective_mode_cache
    if _effective_mode_cache is not None:
        return _effective_mode_cache
    from fleetent.integrations.sandbox.client import SandboxClient

    docker_available = await SandboxClient().docker_available()
    _effective_mode_cache = resolve_effective_mode(load_sandbox_mode(), docker_available)
    return _effective_mode_cache


def _read_raw_mode() -> object | None:
    """Pull `sandbox.mode` out of the settings file, or None when unavailable."""
    if not SETTINGS_PATH.exists():
        return None
    try:
        raw = yaml.safe_load(SETTINGS_PATH.read_text())
    except yaml.YAMLError as exc:
        _logger.warn("settings_yaml_parse_failed", path=str(SETTINGS_PATH), error=str(exc))
        return None
    if not isinstance(raw, dict):
        return None
    section = raw.get("sandbox")
    if not isinstance(section, dict):
        return None
    return section.get("mode")


def resolve_effective_mode(configured: Mode, docker_available: bool) -> Mode:
    """Resolve the runtime-effective mode (D2 degrade): no Docker forces OFF.

    Docker availability is probed once at startup; when absent the platform still
    boots but every agent loses code execution (`run_code` never enters its schema).
    """
    if not docker_available:
        return Mode.OFF
    return configured


def is_code_execution_enabled(mode: Mode, code_execution: bool | None) -> bool:
    """Decide whether `run_code` is enabled for an agent (D1).

    - OFF: always disabled.
    - SELECTIVE: enabled only when the agent explicitly opts in (`True`).
    - ALL: enabled unless the agent explicitly opts out (`False`); `None`/`True` on.
    """
    if mode is Mode.OFF:
        return False
    if mode is Mode.SELECTIVE:
        return code_execution is True
    return code_execution is not False
