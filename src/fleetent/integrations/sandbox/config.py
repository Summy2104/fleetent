"""Sandbox resource configuration (SB4).

Externalises the previously hardcoded `docker run` resource flags
(`--memory`/`--cpus`/`--network`/`--read-only`) into a configurable
`SandboxResources` dataclass loaded from `platform.yaml`'s shared
`sandbox:` section (skeleton owned by SB3). The dataclass defaults are the
single source of truth for the "safe defaults" used when the file, section, or
a field is absent. Loading only overrides what is present and validates each
field, falling back to the default on invalid input rather than silently
accepting it. `exec_timeout` is carried for wave-3 (enforced termination) only;
this change clamps it to [1, 600] but does not act on it in `docker run`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from fleetent import paths
from fleetent.observability.structured_logging import get_logger

_logger = get_logger("sandbox.config")

# Shared with sandbox_enablement.SETTINGS_PATH; an injectable module-level
# constant (no global mutable state) so tests monkeypatch it to an isolated path.
SETTINGS_PATH: Path = paths.platform_yaml_path()

_EXEC_TIMEOUT_MIN = 1
_EXEC_TIMEOUT_MAX = 600

# SB2 lifecycle defaults. `scope` selects container granularity (session-local vs
# per-agent), `idle_hours` is the agent-scope idle TTL before sweep_idle reclaims.
_DEFAULT_SCOPE = "session"
_VALID_SCOPES = ("session", "agent")
_DEFAULT_IDLE_HOURS = 2.0


class NetworkPolicy(StrEnum):
    NONE = "none"
    PUBLIC_ONLY = "public_only"
    ALLOW_ALL = "allow_all"


@dataclass
class SandboxLifecycle:
    """SB2 container-lifecycle policy from the `sandbox:` section.

    `scope` ("session" | "agent") sets container granularity; `idle_hours` is the
    agent-scope idle TTL. SB4 owns resource fields; these two are SB2's additions.
    """

    scope: str = _DEFAULT_SCOPE
    idle_hours: float = _DEFAULT_IDLE_HOURS


@dataclass
class SandboxResources:
    """Per-container resource limits; dataclass defaults are the safe defaults.

    `read_only` belongs to the resource tier (default True keeps session
    containers read-only); SB2 passes False for writable agent containers.
    """

    memory: int = 256
    cpus: float = 0.5
    network: NetworkPolicy = NetworkPolicy.NONE
    exec_timeout: int = 30
    read_only: bool = True


def load_sandbox_resources(path: Path | None = None) -> SandboxResources:
    """Load `sandbox.resources` from settings.yaml, falling back per field.

    Returns all defaults when the file, the `sandbox:` section, or the
    `resources:` subsection is absent. Present-but-invalid individual fields log
    a warning and fall back to that field's default (never silently accepted).
    A corrupt YAML file logs and yields all defaults rather than failing startup.
    """
    return _resources_from_section(_read_resources_section(path or SETTINGS_PATH))


def load_sandbox_lifecycle(path: Path | None = None) -> SandboxLifecycle:
    """Load SB2's `sandbox.scope` / `sandbox.idle_hours`, falling back per field.

    An unrecognised scope or a non-positive idle_hours logs a warning and falls
    back to its default rather than being silently accepted.
    """
    sandbox = _read_sandbox_section(path or SETTINGS_PATH)
    if sandbox is None:
        return SandboxLifecycle()
    return SandboxLifecycle(
        scope=_load_scope(sandbox, _DEFAULT_SCOPE),
        idle_hours=_load_positive_float(sandbox, "idle_hours", _DEFAULT_IDLE_HOURS),
    )


def build_resources_by_scope(path: Path | None = None) -> dict[str, SandboxResources]:
    """Map each scope to its resource tier (SB2's scope→tier strategy).

    `session` uses the hardened `sandbox.resources` tier as-is (read_only stays
    True, network none). `agent` inherits that base, applies the optional
    `sandbox.agent_scope` override, then forces `read_only=False` so the writable
    rootfs can hold installed deps for `docker commit` to capture (D3).
    """
    resolved = path or SETTINGS_PATH
    sandbox = _read_sandbox_section(resolved)
    base = _resources_from_section(_read_resources_section(resolved))

    override = sandbox.get("agent_scope") if isinstance(sandbox, dict) else None
    if not isinstance(override, dict):
        override = {}
    from dataclasses import replace

    agent = replace(
        base,
        memory=_load_positive_int(override, "memory", base.memory),
        cpus=_load_positive_float(override, "cpus", base.cpus),
        network=_load_network(override, base.network),
        read_only=False,
    )
    return {_DEFAULT_SCOPE: base, "agent": agent}


def _load_scope(section: dict[str, object], default: str) -> str:
    if "scope" not in section:
        return default
    value = section["scope"]
    if isinstance(value, str) and value in _VALID_SCOPES:
        return value
    _logger.warn("sandbox_scope_invalid", value=repr(value), falling_back=default)
    return default


def _read_sandbox_section(path: Path) -> dict[str, object] | None:
    """Pull the top-level `sandbox:` mapping out of the settings file, or None.

    A corrupt YAML file or a missing/non-mapping `sandbox` section yields None so
    callers fall back to defaults rather than failing startup.
    """
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        _logger.warn("settings_yaml_parse_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(raw, dict):
        return None
    sandbox = raw.get("sandbox")
    if not isinstance(sandbox, dict):
        return None
    return sandbox


def _read_resources_section(path: Path) -> dict[str, object] | None:
    """Pull `sandbox.resources` out of the settings file, or None when absent."""
    sandbox = _read_sandbox_section(path)
    if sandbox is None:
        return None
    resources = sandbox.get("resources")
    if not isinstance(resources, dict):
        return None
    return resources


def _resources_from_section(section: dict[str, object] | None) -> SandboxResources:
    """Build SandboxResources from a `resources`-shaped mapping (per-field validated)."""
    if section is None:
        return SandboxResources()
    defaults = SandboxResources()
    return SandboxResources(
        memory=_load_positive_int(section, "memory", defaults.memory),
        cpus=_load_positive_float(section, "cpus", defaults.cpus),
        network=_load_network(section, defaults.network),
        exec_timeout=_load_exec_timeout(section, defaults.exec_timeout),
        read_only=_load_read_only(section, defaults.read_only),
    )


def _load_positive_int(section: dict[str, object], key: str, default: int) -> int:
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _logger.warn("sandbox_resource_invalid", field=key, value=repr(value), falling_back=default)
        return default
    return value


def _load_positive_float(section: dict[str, object], key: str, default: float) -> float:
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        _logger.warn("sandbox_resource_invalid", field=key, value=repr(value), falling_back=default)
        return default
    return float(value)


def _load_network(section: dict[str, object], default: NetworkPolicy) -> NetworkPolicy:
    if "network" not in section:
        return default
    value = section["network"]
    try:
        return NetworkPolicy(str(value))
    except ValueError:
        _logger.warn(
            "sandbox_resource_invalid",
            field="network",
            value=repr(value),
            falling_back=default.value,
        )
        return default


def _load_exec_timeout(section: dict[str, object], default: int) -> int:
    """Load exec_timeout, clamping any int to [1, 600]; non-ints fall back.

    Out-of-range integers (e.g. 0 or 1000) are a range-validation concern, so
    they are clamped to the boundary rather than discarded. A non-int value
    (string/None/bool) is malformed and falls back to the default.
    """
    if "exec_timeout" not in section:
        return default
    value = section["exec_timeout"]
    if isinstance(value, bool) or not isinstance(value, int):
        _logger.warn(
            "sandbox_resource_invalid",
            field="exec_timeout",
            value=repr(value),
            falling_back=default,
        )
        return default
    return max(_EXEC_TIMEOUT_MIN, min(_EXEC_TIMEOUT_MAX, value))


def _load_read_only(section: dict[str, object], default: bool) -> bool:
    if "read_only" not in section:
        return default
    value = section["read_only"]
    if not isinstance(value, bool):
        _logger.warn(
            "sandbox_resource_invalid", field="read_only", value=repr(value), falling_back=default
        )
        return default
    return value
