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

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

import yaml

from fleetent import paths
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.config")

# Shared with sandbox_enablement.SETTINGS_PATH; an injectable module-level
# constant (no global mutable state) so tests monkeypatch it to an isolated path.
SETTINGS_PATH: Path = paths.platform_yaml_path()

_EXEC_TIMEOUT_MIN = 1
_EXEC_TIMEOUT_MAX = 600

# Backend selection (sandbox-backend-abstraction). `docker` is the default so existing
# deployments are unchanged; `microsandbox` selects the local-microVM backend.
_DEFAULT_BACKEND = "docker"
_VALID_BACKENDS = ("docker", "microsandbox")


class NetworkPolicy(StrEnum):
    NONE = "none"
    PUBLIC_ONLY = "public_only"
    ALLOW_ALL = "allow_all"


@dataclass
class SkillMountConfig:
    """Skills-mount policy from the `sandbox.skill_mount` section (sandbox-skill-mount).

    `enabled` toggles mounting the host skills root into `/workspace/skills`;
    `read_only` mounts it ro (default) so the agent cannot rewrite skill assets;
    `source` optionally overrides the resolved effective skills root (None → the
    registry's resolved user root). Defaults mount the user root read-only.
    """

    enabled: bool = True
    read_only: bool = True
    source: str | None = None


@dataclass
class SandboxBackendConfig:
    """Backend selection from the `sandbox:` section (sandbox-backend-abstraction).

    `backend` is the platform-level default backend name; `microsandbox_image` is the
    optional base image for the microsandbox backend. The factory resolves the final
    backend by overlaying any per-agent `agent.yaml` override on top of this.
    """

    backend: str = _DEFAULT_BACKEND
    microsandbox_image: str | None = None
    docker_image: str | None = None


def _image_from_subsection(sandbox: dict[str, object], key: str) -> str | None:
    """Read `sandbox.<key>.image` as a non-blank string, else None."""
    sub = sandbox.get(key)
    image = sub.get("image") if isinstance(sub, dict) else None
    return image if isinstance(image, str) and image.strip() else None


def load_sandbox_backend_config(path: Path | None = None) -> SandboxBackendConfig:
    """Load `sandbox.backend` / `sandbox.{microsandbox,docker}.image`, falling back to docker.

    An unrecognised backend logs a warning and falls back to `docker` rather than
    being silently accepted (mirrors the resource-config "never silently accept"
    rule). A missing file / section yields all defaults.
    """
    sandbox = _read_sandbox_section(path or SETTINGS_PATH)
    if sandbox is None:
        return SandboxBackendConfig()
    backend = _load_backend(sandbox, _DEFAULT_BACKEND)
    return SandboxBackendConfig(
        backend=backend,
        microsandbox_image=_image_from_subsection(sandbox, "microsandbox"),
        docker_image=_image_from_subsection(sandbox, "docker"),
    )


def _load_backend(section: dict[str, object], default: str) -> str:
    if "backend" not in section:
        return default
    value = section["backend"]
    if isinstance(value, str) and value in _VALID_BACKENDS:
        return value
    _logger.warn("sandbox_backend_invalid", value=repr(value), falling_back=default)
    return default


@dataclass
class SandboxResources:
    """Per-container resource limits; dataclass defaults are the safe defaults.

    `read_only` belongs to the resource tier (default True keeps containers read-only);
    containers run read-only now that deps are baked into a build-time immutable image
    rather than installed at runtime.

    The hardening fields default to the strictest tier — a bare `SandboxResources()` is
    the single source of truth for that tier. Per-agent-sandbox-resources: each agent has
    one resource profile built from `agent.yaml` `sandbox.resources` via
    `resources_from_agent_settings` (session/agent workspace scopes share it).
    """

    memory: int = 256
    cpus: float = 0.5
    network: NetworkPolicy = NetworkPolicy.NONE
    exec_timeout: int = 30
    read_only: bool = True
    # 内存硬上限（sandbox-memory-hard-limit）：None → --memory-swap 等于 memory（禁 swap，
    # 内存限制即硬 RAM 上限）；正整数 → memory+swap 总额（MB）。钳制见 client._resource_flags。
    memory_swap_mb: int | None = None
    # Container hardening (sandbox-container-hardening).
    pids_limit: int = 256
    tmpfs_size_mb: int = 64
    cap_drop_all: bool = True
    cap_add: tuple[str, ...] = ()
    no_new_privileges: bool = True
    init: bool = True
    run_as_user: str | None = "65534:65534"


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
        memory_swap_mb=_load_optional_positive_int(
            section, "memory_swap_mb", defaults.memory_swap_mb
        ),
        pids_limit=_load_positive_int(section, "pids_limit", defaults.pids_limit),
        tmpfs_size_mb=_load_positive_int(section, "tmpfs_size_mb", defaults.tmpfs_size_mb),
        cap_drop_all=_load_bool(section, "cap_drop_all", defaults.cap_drop_all),
        no_new_privileges=_load_bool(section, "no_new_privileges", defaults.no_new_privileges),
        init=_load_bool(section, "init", defaults.init),
        run_as_user=_load_run_as_user(section, defaults.run_as_user),
    )


def resources_from_agent_settings(resources: object) -> SandboxResources:
    """Build `SandboxResources` from a per-agent `SandboxResourcesSettings`.

    Per-agent-sandbox-resources: each agent owns one resource/hardening profile in its
    `agent.yaml` `sandbox.resources`; this replaces the machine-shared `platform.yaml`
    `sandbox.resources` (+ `agent_scope`) path. `None` fields inherit the code-level safe
    default; declared fields reuse the exact same value-level validation/clamp/enum-fallback
    as `_resources_from_section` (invalid values fall back with a warning, never rejected).
    """
    if resources is None:
        return SandboxResources()
    declared = {k: v for k, v in resources.model_dump().items() if v is not None}  # type: ignore[attr-defined]
    base = _resources_from_section(declared)
    # cap_add is not covered by _resources_from_section (it has no platform.yaml precedent
    # in that builder); apply it explicitly from the agent profile.
    cap_add = declared.get("cap_add")
    if cap_add is not None:
        base = replace(base, cap_add=_coerce_cap_add(cap_add, base.cap_add))
    return base


def _coerce_cap_add(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    """Coerce `cap_add` to a tuple of non-empty capability strings; invalid → default."""
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(c, str) and c.strip() for c in value
    ):
        _logger.warn(
            "sandbox_resource_invalid", field="cap_add", value=repr(value), falling_back=default
        )
        return default
    return tuple(value)


def _load_positive_int(section: dict[str, object], key: str, default: int) -> int:
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _logger.warn("sandbox_resource_invalid", field=key, value=repr(value), falling_back=default)
        return default
    return value


def _load_optional_positive_int(
    section: dict[str, object], key: str, default: int | None
) -> int | None:
    """Load an optional positive int; missing → default, invalid → default (with warn).

    Distinct from `_load_positive_int` because the field's default is ``None`` (not an
    int): absent keeps the inherited default, a present-but-invalid value falls back to
    it rather than being silently accepted.
    """
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


def _load_bool(section: dict[str, object], key: str, default: bool) -> bool:
    """Load a strict bool field; a non-bool (e.g. the string "yes") falls back.

    YAML already maps `true`/`false`/`yes`/`no` keywords to bools, so a value that
    survives as a non-bool here is a quoted string or other malformed input and is
    rejected rather than coerced to a truthy/falsy value.
    """
    if key not in section:
        return default
    value = section[key]
    if not isinstance(value, bool):
        _logger.warn("sandbox_resource_invalid", field=key, value=repr(value), falling_back=default)
        return default
    return value


def _load_read_only(section: dict[str, object], default: bool) -> bool:
    return _load_bool(section, "read_only", default)


def _load_run_as_user(section: dict[str, object], default: str | None) -> str | None:
    """Load run_as_user: a non-empty string, or explicit null (= run as root).

    An explicit YAML `null` (→ None) is a valid value meaning "no --user, run as
    the image's default user (root)". A non-string, non-null value is malformed
    and falls back to the default rather than being silently accepted.
    """
    if "run_as_user" not in section:
        return default
    value = section["run_as_user"]
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    _logger.warn(
        "sandbox_resource_invalid", field="run_as_user", value=repr(value), falling_back=default
    )
    return default
