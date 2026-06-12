"""Sandbox hardening primitives: mount-path blocklist + config-hash (sandbox-hardening).

Pure, side-effect-free helpers so the manager/client can (a) refuse to bind-mount a
host directory that resolves into a sensitive area, and (b) detect when a reused
container was created under a now-stale configuration. No platform imports.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

# Host roots that must never be bind-mounted into a sandbox container. Home-relative
# entries resolve against the running user's home at call time; absolute entries are
# system areas. The workspace dir normally lives under the repo/data tree, well clear
# of these — this guard catches a misconfigured FLEETENT_HOME pointing at a sensitive
# location.
_HOME_RELATIVE_BLOCKED = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".config/gcloud")
_ABSOLUTE_BLOCKED = ("/etc", "/root", "/var/run", "/proc", "/sys", "/boot")


def _blocked_roots() -> list[str]:
    home = str(Path.home())
    roots = [os.path.join(home, rel) for rel in _HOME_RELATIVE_BLOCKED]
    roots += list(_ABSOLUTE_BLOCKED)
    return [os.path.realpath(r) for r in roots]


def is_blocked_mount(path: str | Path) -> bool:
    """Whether ``path`` resolves to, or inside, a blocked host root.

    ``realpath`` follows symlinks on the existing prefix so a symlinked path cannot
    sneak a blocked target past the prefix check.
    """
    resolved = os.path.realpath(str(path))
    return any(resolved == root or resolved.startswith(root + os.sep) for root in _blocked_roots())


def config_hash(
    image: str | None,
    resources: Any,
    env: dict[str, str] | None,
    workspace_host_path: str | None,
    skill_mount: Any = None,
) -> str:
    """Stable short digest of the container's effective configuration.

    Used to invalidate a reused container when its config changed. Env contributes
    only its *key set* (sorted), not values — rotating a value should not force a
    rebuild, only changing which variables are injected. ``skill_mount``
    (sandbox-skill-mount) contributes its host source + ro/rw mode so changing the
    mounted skills root (or its writability) rebuilds a reused container; ``None``
    leaves the payload byte-identical to the pre-skill-mount signature so existing
    containers are not invalidated by the new parameter alone.
    """
    resource_fields = sorted(vars(resources).items()) if resources is not None else []
    payload_dict: dict[str, Any] = {
        "image": image or "",
        "resources": resource_fields,
        "env_keys": sorted((env or {}).keys()),
        "workspace": workspace_host_path or "",
    }
    if skill_mount is not None:
        payload_dict["skill_mount"] = [skill_mount.host_src, skill_mount.read_only]
    payload = json.dumps(
        payload_dict,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
