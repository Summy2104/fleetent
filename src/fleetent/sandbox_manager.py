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

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from fleetent.sandbox_client import _SAFE_NAME, SANDBOX_NAME_PREFIX, SandboxClient
from fleetent.sandbox_config import (
    SandboxResources,
    build_resources_by_scope,
    load_sandbox_lifecycle,
)

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


def _sanitise(raw: str) -> str:
    """Reuse the client's safe-name policy + 48-char cap for the name key."""
    return _SAFE_NAME.sub("-", raw)[:48]


def _container_name(scope: Scope, key: str) -> str:
    return f"{SANDBOX_NAME_PREFIX}{scope.value}-{_sanitise(key)}"


def _agent_image_tag(key: str) -> str:
    return _AGENT_IMAGE_TPL.format(key=_sanitise(key))


@dataclass
class SandboxManager:
    """Per-process sandbox lifecycle owner; registry is instance state.

    `scope` / `idle_hours` / `resources_by_scope` default from config but are
    fully injectable for isolated tests; `clock` is injectable so idle sweeps are
    deterministic without real time.
    """

    client: SandboxClient = field(default_factory=SandboxClient)
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

    async def acquire(self, scope: Scope, session_id: str, agent_name: str) -> str:
        """Return a workspace id for (scope, key), reusing or creating as needed.

        The key is the session id for `session` scope, the agent name for `agent`
        scope. A registry hit refreshes last_used; a live container found by name
        is re-adopted; otherwise a new container is created with the scope's tier
        (and, for agent scope, a committed dependency image when one exists).
        """
        key = session_id if scope is Scope.SESSION else agent_name
        name = _container_name(scope, key)
        now = self.clock()

        entry = self._registry.get(name)
        if entry is not None:
            entry.last_used = now
            return entry.workspace_id

        existing = await self.client.find_workspace(name)
        if existing is not None:
            self._registry[name] = _Entry(existing, scope, key, now)
            return existing

        image = await self._image_for(scope, key)
        workspace_id = await self.client.create_workspace(
            name=name, resources=self.resources_for(scope), image=image
        )
        self._registry[name] = _Entry(workspace_id, scope, key, now)
        return workspace_id

    async def _image_for(self, scope: Scope, key: str) -> str | None:
        """Agent scope boots from its committed image when present, else default."""
        if scope is not Scope.AGENT:
            return None
        tag = _agent_image_tag(key)
        if await self.client.image_exists(tag):
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

    async def release_session(self, session_id: str) -> None:
        """Destroy the `session`-scope container for this session, if registered.

        No-op for sessions with no session-scope container (e.g. agent scope);
        other sessions' containers are untouched.
        """
        name = _container_name(Scope.SESSION, session_id)
        entry = self._registry.get(name)
        if entry is None or entry.scope is not Scope.SESSION:
            return
        await self.client.destroy_workspace(entry.workspace_id)
        self._registry.pop(name, None)

    async def sweep_idle(self) -> None:
        """Reclaim agent-scope containers idle past `idle_hours`.

        Each reclaimed container is committed to its dependency image first, then
        destroyed (commit-then-destroy) so the next acquire can boot from it.
        Session scope never participates in idle reclamation.
        """
        now = self.clock()
        cutoff = self.idle_hours * 3600
        stale = [
            entry
            for entry in self._registry.values()
            if entry.scope is Scope.AGENT and (now - entry.last_used) > cutoff
        ]
        for entry in stale:
            await self.client.commit_workspace(entry.workspace_id, _agent_image_tag(entry.key))
            await self.client.destroy_workspace(entry.workspace_id)
            self._registry.pop(_container_name(entry.scope, entry.key), None)
