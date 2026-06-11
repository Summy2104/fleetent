"""Sandbox container lifecycle management (SB2).

Owns the "scope→tier" mapping and the container lifecycle atop SB3's context
channel and SB4's `SandboxResources`. A `SandboxManager` instance holds its own
in-memory registry (no module-global mutable state, per CLAUDE.md): tests build
isolated instances and inject a mocked `SandboxClient` and clock.

Container naming encodes ownership as `sandbox-{scope}-{sanitised key}` (the
`sandbox-` prefix constant lives in `sandbox_client.py`, the lowest layer, shared
with SB8's orphan enumeration). `session` scope keeps the hardened tier and is
reclaimed on `release_session`; `agent` scope runs writable, is committed to a
dependency image then destroyed by `sweep_idle` once idle past `idle_hours`.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from fleetent import paths
from fleetent.integrations.sandbox.backend import (
    _SAFE_NAME,
    SANDBOX_NAME_PREFIX,
    BaseSandboxBackend,
)
from fleetent.integrations.sandbox.backends.docker import DockerBackend
from fleetent.integrations.sandbox.config import (
    SandboxResources,
    build_resources_by_scope,
    load_sandbox_lifecycle,
)
from fleetent.integrations.sandbox.hardening import config_hash, is_blocked_mount
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.manager")

# Image tag committed for an agent-scope container's dependencies; the next
# acquire boots from it when present, else falls back to the client default.
_AGENT_IMAGE_TPL = "fleetent-sandbox-agent-{key}:latest"


class Scope(StrEnum):
    SESSION = "session"
    AGENT = "agent"


@dataclass
class _Entry:
    workspace_id: str
    scope: Scope
    key: str
    last_used: float


# Total budget for the name-key segment that follows `sandbox-{scope}-`. The longest
# scope prefix is `sandbox-session-` (16 chars); a 47-char budget keeps the full
# container name within Docker's 63-char limit. Workspace subdir names (filesystem
# limit 255) reuse the same budget so container and workspace derivation stay identical.
_NAME_KEY_BUDGET = 47
# Length of the collision-resisting hash suffix appended when truncation is required.
# Derived from the full (untruncated) key so two keys sharing a >budget prefix but
# differing in the truncated tail still map to distinct names.
_HASH_SUFFIX_LEN = 12


def _sanitise(raw: str) -> str:
    """Apply the shared safe-name policy (no length cap)."""
    return _SAFE_NAME.sub("-", raw)


def _name_key(raw: str) -> str:
    """Derive a collision-free, length-bounded name key from a full ownership key.

    Short keys pass through the sanitiser verbatim (human-readable container /
    workspace names for the common case). Once the sanitised key exceeds the
    name-key budget, a `sha256` suffix computed over the **full untruncated** key is
    appended to a truncated readable prefix, so two keys sharing a prefix longer than
    the budget but differing only in the truncated tail still derive to distinct
    names. The suffix is lowercase hex, keeping the result Docker-name-legal.

    Args:
        raw: The full, untruncated ownership key (session id or agent name).

    Returns:
        A sanitised name key no longer than ``_NAME_KEY_BUDGET`` chars.
    """
    sanitised = _sanitise(raw)
    if len(sanitised) <= _NAME_KEY_BUDGET:
        return sanitised
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_HASH_SUFFIX_LEN]
    prefix_budget = _NAME_KEY_BUDGET - _HASH_SUFFIX_LEN - 1  # 1 for the joining dash
    return f"{sanitised[:prefix_budget]}-{digest}"


def _container_name(scope: Scope, key: str) -> str:
    return f"{SANDBOX_NAME_PREFIX}{scope.value}-{_name_key(key)}"


def _agent_image_tag(key: str) -> str:
    return _AGENT_IMAGE_TPL.format(key=_name_key(key))


@dataclass
class SandboxManager:
    """Per-process sandbox lifecycle owner; registry is instance state.

    `scope` / `idle_hours` / `resources_by_scope` default from config but are
    fully injectable for isolated tests; `clock` is injectable so idle sweeps are
    deterministic without real time.
    """

    backend: BaseSandboxBackend = field(default_factory=DockerBackend)
    scope: Scope = field(default=Scope.SESSION)
    idle_hours: float = 2.0
    resources_by_scope: dict[Scope, SandboxResources] | None = None
    clock: Callable[[], float] = time.monotonic
    _registry: dict[str, _Entry] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.resources_by_scope is None:
            lifecycle = load_sandbox_lifecycle()
            by_scope = build_resources_by_scope()
            self.resources_by_scope = {
                Scope.SESSION: by_scope[Scope.SESSION.value],
                Scope.AGENT: by_scope[Scope.AGENT.value],
            }
            # Honour config defaults only when the caller left them unset.
            if self.scope == Scope.SESSION and self.idle_hours == 2.0:
                self.scope = Scope(lifecycle.scope)
                self.idle_hours = lifecycle.idle_hours
        else:
            self.resources_by_scope = {Scope(k): v for k, v in self.resources_by_scope.items()}

    def resources_for(self, scope: Scope) -> SandboxResources:
        assert self.resources_by_scope is not None
        return self.resources_by_scope[scope]

    async def acquire(
        self,
        scope: Scope,
        session_id: str,
        agent_name: str,
        env: dict[str, str] | None = None,
    ) -> str:
        """Return a workspace id for (scope, key), reusing or creating as needed.

        The key is the session id for `session` scope, the agent name for `agent`
        scope. A registry hit refreshes last_used; a live container found by name
        is re-adopted; otherwise a new container is created with the scope's tier
        (and, for agent scope, a committed dependency image when one exists).

        `env` (SB5) is the already-filtered injection mapping threaded to
        create_workspace on a fresh create; reused/re-adopted containers keep the
        env they were created with. None preserves SB2's clean-environment default.
        """
        key = session_id if scope is Scope.SESSION else agent_name
        name = _container_name(scope, key)
        now = self.clock()

        entry = self._registry.get(name)
        if entry is not None:
            # Verify-on-reuse: a container can die outside our control (OOM kill,
            # manual rm, daemon restart). Handing a dead id to the exec layer would
            # break every sandbox-backed tool for the rest of the session, so a
            # registry hit must be confirmed live; a dead entry falls through to
            # the adopt-or-create path (the host-mounted workspace survives, so a
            # rebuilt container sees the same files).
            live = await self.backend.find_workspace(name)
            if live is not None:
                entry.last_used = now
                return entry.workspace_id
            _logger.warn("sandbox_registry_stale_container", name=name)
            self._registry.pop(name, None)

        image = await self._image_for(scope, key)
        # workspace_mount capability: only backends that bind-mount a host dir get a
        # host path; others run with an instance-local /workspace (degraded, logged).
        if self.backend.capabilities.workspace_mount:
            ws_path: Path | None = self.workspace_host_path(scope, session_id, agent_name)
        else:
            ws_path = None
            _logger.debug(
                "sandbox_workspace_mount_unsupported", backend=self.backend.name, name=name
            )
        host_path = str(ws_path) if ws_path is not None else None
        desired_hash = config_hash(image, self.resources_for(scope), env, host_path)

        existing = await self.backend.find_workspace(name)
        if existing is not None:
            # sandbox-hardening: re-adopt a surviving container only if its config-hash
            # still matches (or is absent on a pre-label container, reused conservatively);
            # a mismatch means the config changed since it was built, so rebuild.
            actual_hash = await self.backend.inspect_config_hash(name)
            if actual_hash is None or actual_hash == desired_hash:
                self._registry[name] = _Entry(existing, scope, key, now)
                return existing
            await self.backend.destroy_workspace(name)
            self._registry.pop(name, None)

        # Session tier runs as `nobody`; make the host workspace dir writable by the
        # container's run uid. Single-tenant on-prem: workspace holds only the agent's
        # own working data (see design risk: mount-point uid write permission).
        if ws_path is not None:
            ws_path.chmod(0o777)
        workspace_id = await self.backend.create_workspace(
            name=name,
            resources=self.resources_for(scope),
            image=image,
            env=env,
            workspace_host_path=host_path,
            config_hash=desired_hash,
        )
        self._registry[name] = _Entry(workspace_id, scope, key, now)
        return workspace_id

    async def _image_for(self, scope: Scope, key: str) -> str | None:
        """Agent scope boots from its committed image when present, else default.

        Only meaningful on backends that can persist deps into an image; backends
        without `persist_workspace` always boot from the base image (None).
        """
        if scope is not Scope.AGENT:
            return None
        if not self.backend.capabilities.persist_workspace:
            return None
        tag = _agent_image_tag(key)
        if await self.backend.image_exists(tag):
            return tag
        return None

    def forget(self, name: str) -> None:
        """Drop a registry entry whose container was destroyed out-of-band.

        run_code's cancel path force-destroys the container (AR19 hard abort); it
        calls this so the next acquire's `find_workspace` miss rebuilds cleanly.
        """
        self._registry.pop(name, None)

    def container_name(self, scope: Scope, session_id: str, agent_name: str) -> str:
        """Public name resolver so callers (run_code) can forget by name on abort."""
        key = session_id if scope is Scope.SESSION else agent_name
        return _container_name(scope, key)

    def invalidate(self, scope: Scope, session_id: str, agent_name: str) -> None:
        """Drop the (scope, key) registration so the next acquire rebuilds.

        Called by exec-layer self-healing when a command hits a missing-container
        error after acquire (the verify-then-die race window).
        """
        key = session_id if scope is Scope.SESSION else agent_name
        self._registry.pop(_container_name(scope, key), None)

    def workspace_host_path(self, scope: Scope, session_id: str, agent_name: str) -> Path:
        """Return (creating) the host dir mounted at ``/workspace`` for (scope, key).

        Shared by `acquire` (the bind-mount source) and the file tools' host-degrade
        backend (the path fence root), so both agree on exactly one directory per
        scope key. Idempotent: creates the dir tree if missing.
        """
        key = session_id if scope is Scope.SESSION else agent_name
        ws_path = paths.workspaces_dir() / _name_key(key)
        # sandbox-hardening: never bind-mount a host dir under a sensitive root (a
        # misconfigured FLEETENT_HOME could otherwise expose ~/.ssh, /etc, etc.).
        # Checked before mkdir so a blocked path leaves no directory behind.
        if is_blocked_mount(ws_path):
            raise ValueError(f"refusing to mount workspace under a blocked host path: {ws_path}")
        ws_path.mkdir(parents=True, exist_ok=True)
        return ws_path

    async def release_session(self, session_id: str) -> None:
        """Destroy the `session`-scope container for this session, if registered.

        No-op for sessions with no session-scope container (e.g. agent scope);
        other sessions' containers are untouched.
        """
        name = _container_name(Scope.SESSION, session_id)
        entry = self._registry.get(name)
        if entry is None or entry.scope is not Scope.SESSION:
            return
        await self.backend.destroy_workspace(entry.workspace_id)
        self._registry.pop(name, None)

    async def sweep_idle(self) -> None:
        """Reclaim agent-scope containers idle past `idle_hours`.

        On a backend that supports `persist_workspace`, each reclaimed container is
        committed to its dependency image first, then destroyed (commit-then-destroy)
        so the next acquire can boot from it. On a backend without that capability,
        the commit is skipped (a warning is logged) and the container is destroyed
        directly — the next acquire reinstalls deps. Session scope never participates.
        """
        # Imported lazily: workspace_gc imports _name_key from this module, so a
        # top-level import here would close an import cycle.
        from fleetent.integrations.sandbox import workspace_gc

        now = self.clock()
        cutoff = self.idle_hours * 3600
        stale = [
            entry
            for entry in self._registry.values()
            if entry.scope is Scope.AGENT and (now - entry.last_used) > cutoff
        ]
        persist = self.backend.capabilities.persist_workspace
        for entry in stale:
            if persist:
                await self.backend.commit_workspace(entry.workspace_id, _agent_image_tag(entry.key))
            else:
                _logger.warn(
                    "sandbox_idle_reclaim_no_persist",
                    backend=self.backend.name,
                    key=entry.key,
                )
            await self.backend.destroy_workspace(entry.workspace_id)
            self._registry.pop(_container_name(entry.scope, entry.key), None)

        # sandbox-workspace-gc: prune stale entries inside every known agent-scope
        # workspace dir by mtime (the dir is cross-session shared, so it is never
        # deleted wholesale, unlike session scope). Run after reclaim so a just-swept
        # agent's dir is included. Best-effort — a prune failure must not abort sweep.
        agent_keys = {e.key for e in self._registry.values() if e.scope is Scope.AGENT}
        agent_keys.update(e.key for e in stale)
        for key in agent_keys:
            try:
                workspace_gc.gc_agent_workspace(key)
            except OSError as exc:
                _logger.warn("sandbox_agent_workspace_gc_failed", key=key, error=str(exc))
