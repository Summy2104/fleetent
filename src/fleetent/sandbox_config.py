"""Sandbox resource configuration (SB4).

Externalises the previously hardcoded `docker run` resource flags
(`--memory`/`--cpus`/`--network`/`--read-only`) into a configurable
`SandboxResources` dataclass loaded from `config/settings.yaml`'s shared
`sandbox:` section (skeleton owned by SB3). The dataclass defaults are the
single source of truth for the "safe defaults" used when the file, section, or
a field is absent. Loading only overrides what is present and validates each
field, falling back to the default on invalid input rather than silently
accepting it. `exec_timeout` is carried for wave-3 (enforced termination) only;
this change clamps it to [1, 600] but does not act on it in `docker run`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Shared with sandbox_enablement.SETTINGS_PATH; an injectable module-level
# constant (no global mutable state) so tests monkeypatch it to an isolated path.
SETTINGS_PATH: Path = Path("config/settings.yaml")

_EXEC_TIMEOUT_MIN = 1
_EXEC_TIMEOUT_MAX = 600


class NetworkPolicy(StrEnum):
    NONE = "none"
    PUBLIC_ONLY = "public_only"
    ALLOW_ALL = "allow_all"


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
    section = _read_resources_section(path or SETTINGS_PATH)
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


def _read_resources_section(path: Path) -> dict[str, object] | None:
    """Pull `sandbox.resources` out of the settings file, or None when absent."""
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        logger.warning("settings_yaml_parse_failed path=%s error=%s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    sandbox = raw.get("sandbox")
    if not isinstance(sandbox, dict):
        return None
    resources = sandbox.get("resources")
    if not isinstance(resources, dict):
        return None
    return resources


def _load_positive_int(section: dict[str, object], key: str, default: int) -> int:
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        logger.warning(
            "sandbox_resource_invalid field=%s value=%r falling_back=%s", key, value, default
        )
        return default
    return value


def _load_positive_float(section: dict[str, object], key: str, default: float) -> float:
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        logger.warning(
            "sandbox_resource_invalid field=%s value=%r falling_back=%s", key, value, default
        )
        return default
    return float(value)


def _load_network(section: dict[str, object], default: NetworkPolicy) -> NetworkPolicy:
    if "network" not in section:
        return default
    value = section["network"]
    try:
        return NetworkPolicy(str(value))
    except ValueError:
        logger.warning(
            "sandbox_resource_invalid field=network value=%r falling_back=%s", value, default.value
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
        logger.warning(
            "sandbox_resource_invalid field=exec_timeout value=%r falling_back=%s", value, default
        )
        return default
    return max(_EXEC_TIMEOUT_MIN, min(_EXEC_TIMEOUT_MAX, value))


def _load_read_only(section: dict[str, object], default: bool) -> bool:
    if "read_only" not in section:
        return default
    value = section["read_only"]
    if not isinstance(value, bool):
        logger.warning(
            "sandbox_resource_invalid field=read_only value=%r falling_back=%s", value, default
        )
        return default
    return value
