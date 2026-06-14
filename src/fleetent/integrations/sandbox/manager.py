"""Sandbox container lifecycle management (SB2).

Owns the container lifecycle atop SB3's context channel and SB4's
`SandboxResources`. A `SandboxManager` instance holds its own in-memory registry
(no module-global mutable state, per CLAUDE.md): tests build isolated instances and
inject a mocked `SandboxClient` and clock.

Two orthogonal dimensions (sandbox-workspace-scope-split):

- **`workspace_scope`** (`WorkspaceScope`, `session` default | `agent`) controls only
  *data isolation* granularity: the container name key, the workspace host dir key,
  and the container's liveness ownership (process-isolation boundary). Container
  naming encodes it as `sandbox-{workspace_scope}-{sanitised key}` (the `sandbox-`
  prefix constant lives in `backend.py`, the lowest layer, shared with SB8's orphan
  enumeration). Multi-user deployments MUST run `session` (a configured `agent` is
  corrected to `session` with a warning, since `agent` data isolation would share one
  workspace dir/container across all users — cross-user leakage).
- **per-agent dependency image persistence** is an *independent* switch. When enabled
  on a `persist_workspace` backend, dependencies are baked offline into an immutable
  deps image (declarative `setup_command`); runtime containers boot read-only from it.
  Image selection is decoupled from `workspace_scope` and never derives from it.

`docker commit`-from-running-container is **retired** from the lifecycle hot path:
`sweep_idle` only reclaims idle containers (no commit), and `_image_for` queries the
declaratively built immutable deps image, never a from-running commit product.
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
    SkillMount,
)
from fleetent.integrations.sandbox.backends.docker import DockerBackend
from fleetent.integrations.sandbox.config import (
    SandboxResources,
    SkillMountConfig,
    build_resources_by_scope,
    load_sandbox_lifecycle,
    load_skill_mount_config,
)
from fleetent.integrations.sandbox.hardening import config_hash, is_blocked_mount
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.manager")

# Image tag for an agent's declaratively built immutable dependency image. Distinct
# from the retired commit-from-running tag (`fleetent-sandbox-agent-*`): this one is
# produced by an offline build of `setup_command` (sandbox-image-persistence), never
# by committing a container that ran end-user code. The next acquire boots read-only
# from it when present, else falls back to the backend default base image.
_DEPS_IMAGE_TPL = "fleetent-sandbox-deps-{key}:latest"


class WorkspaceScope(StrEnum):
    """Data-isolation granularity (sandbox-workspace-scope).

    Controls only the container name key, workspace host dir key, and container
    liveness ownership — NOT dependency image persistence (that is an independent
    per-agent switch, see `sandbox-image-persistence`).
    """

    SESSION = "session"
    AGENT = "agent"


# Re-export alias: keeps existing `Scope` / `Scope.SESSION` / `Scope.AGENT` imports
# working after the rename (the shim carries no logic, per CLAUDE.md).
Scope = WorkspaceScope


@dataclass
class _Entry:
    workspace_id: str
    scope: WorkspaceScope
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


def _container_name(scope: WorkspaceScope, key: str) -> str:
    return f"{SANDBOX_NAME_PREFIX}{scope.value}-{_name_key(key)}"


def _deps_image_tag(key: str) -> str:
    """Tag of the declaratively built immutable deps image for an agent key."""
    return _DEPS_IMAGE_TPL.format(key=_name_key(key))


def resolve_workspace_scope(configured: WorkspaceScope, *, multi_user: bool) -> WorkspaceScope:
    """Return the effective workspace_scope, enforcing the multi-user guard.

    Multi-user deployments MUST run `session` data isolation: a configured `agent`
    scope would share one workspace dir/container across all users (cross-user
    leakage). When `multi_user` is True a configured `agent` is corrected to `session`
    and a warning is logged — never silently accepted. Single-user (standalone) runs
    keep the configured scope (an `agent` scope there has no cross-user surface and
    enables cross-session dependency reuse).
    """
    if multi_user and configured is WorkspaceScope.AGENT:
        _logger.warn("sandbox_workspace_scope_agent_corrected_multi_user", forced="session")
        return WorkspaceScope.SESSION
    return configured


def workspace_scope_key(scope: WorkspaceScope, session_id: str, agent_name: str) -> str:
    """The single source of truth for a run's workspace scope key (D0).

    `session` scope keys per session (`session_id`); `agent` scope keys per agent
    (`agent_name`). This is the one key that both `/workspace` (sandbox mount) and
    `/exchange` (file-exchange attribution/view) derive from — they MUST agree, so
    every site computes it here rather than re-deriving inline.
    """
    return session_id if scope is WorkspaceScope.SESSION else agent_name


@dataclass
class SandboxManager:
    """Per-process sandbox lifecycle owner; registry is instance state.

    Two orthogonal dimensions (sandbox-workspace-scope-split):

    - `scope` (the `workspace_scope`) sets data-isolation granularity only.
    - `image_persistence` (+ `setup_command`) is the independent per-agent
      dependency-image switch; image selection never derives from `scope`.

    `multi_user` reflects the run shape: platform-hosted shared IM ingress sets it
    True, standalone single-user `fleetent agent run` leaves it False. When True a
    configured `agent` workspace_scope is corrected to `session` (cross-user leakage
    guard). `scope` / `idle_hours` / `resources_by_scope` default from config but are
    fully injectable for isolated tests; `clock` is injectable so idle sweeps are
    deterministic without real time.
    """

    backend: BaseSandboxBackend = field(default_factory=DockerBackend)
    scope: WorkspaceScope = field(default=WorkspaceScope.SESSION)
    idle_hours: float = 2.0
    resources_by_scope: dict[WorkspaceScope, SandboxResources] | None = None
    skill_mount: SkillMountConfig | None = None
    multi_user: bool = False
    image_persistence: bool = False
    setup_command: str | None = None
    clock: Callable[[], float] = time.monotonic
    _registry: dict[str, _Entry] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.skill_mount is None:
            self.skill_mount = load_skill_mount_config()
        if self.resources_by_scope is None:
            lifecycle = load_sandbox_lifecycle()
            by_scope = build_resources_by_scope()
            self.resources_by_scope = {
                WorkspaceScope.SESSION: by_scope[WorkspaceScope.SESSION.value],
                WorkspaceScope.AGENT: by_scope[WorkspaceScope.AGENT.value],
            }
            # Honour config defaults only when the caller left them unset.
            if self.scope == WorkspaceScope.SESSION and self.idle_hours == 2.0:
                self.scope = WorkspaceScope(lifecycle.workspace_scope)
                self.idle_hours = lifecycle.idle_hours
        else:
            self.resources_by_scope = {
                WorkspaceScope(k): v for k, v in self.resources_by_scope.items()
            }
        # Multi-user guard (sandbox-workspace-scope): `agent` data isolation shares one
        # workspace dir/container across all users — a cross-user leakage foot-gun. In a
        # multi-user run shape, force `session` and warn rather than silently accept it.
        self.scope = resolve_workspace_scope(self.scope, multi_user=self.multi_user)

    def resources_for(self, scope: WorkspaceScope) -> SandboxResources:
        assert self.resources_by_scope is not None
        return self.resources_by_scope[scope]

    def _resolve_skill_mount(self) -> SkillMount | None:
        """Resolve the skills bind-mount for a fresh create, or None when off (D2-D4).

        Returns None when the skill mount is disabled or the backend cannot bind-mount
        (degraded backends fall back to the OFF skills-supply contract elsewhere).
        Otherwise resolves the effective (user) skills root, materializes package
        builtin skills into it so their resources are reachable under `$SKILLS_DIR`,
        and validates the source against `is_blocked_mount` before constructing the
        `SkillMount` — a source under a sensitive root raises rather than mounting.
        """
        cfg = self.skill_mount
        if cfg is None or not cfg.enabled:
            return None
        if not self.backend.capabilities.workspace_mount:
            return None
        # Lazy import: skills.registry is a sibling agent-runtime package; importing it
        # at module load would risk a cycle through paths/agent_config.
        from fleetent.skills import registry as skill_registry

        source = cfg.source
        root = skill_registry.effective_skill_root(source)
        skill_registry.materialize_builtin_skills(source)
        if is_blocked_mount(root):
            raise ValueError(f"refusing to mount skills under a blocked host path: {root}")
        return SkillMount(host_src=str(root), read_only=cfg.read_only)

    async def acquire(
        self,
        scope: WorkspaceScope,
        session_id: str,
        agent_name: str,
        env: dict[str, str] | None = None,
    ) -> str:
        """Return a workspace id for (workspace_scope, key), reusing or creating.

        Two independent dimensions (sandbox-workspace-scope-split):

        - **Container name / workspace path** derive from `workspace_scope`: the key is
          the session id for `session` scope, the agent name for `agent` scope. A
          registry hit refreshes last_used; a live container found by name is
          re-adopted; otherwise a new container is created with the scope's tier.
        - **Image selection** is a *separate* branch (`_image_for`) driven only by the
          per-agent image-persistence switch + backend capability — never by
          `workspace_scope`. It is always keyed on the agent name (the deps image is
          per-agent), so the same image choice results under either workspace_scope.

        `env` (SB5) is the already-filtered injection mapping threaded to
        create_workspace on a fresh create; reused/re-adopted containers keep the
        env they were created with. None preserves SB2's clean-environment default.
        """
        key = workspace_scope_key(scope, session_id, agent_name)
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

        # Image selection走独立分支:只看 per-agent 持久化开关 + 后端能力,与 workspace_scope
        # 解耦,且始终以 agent_name 为键(deps 镜像是 per-agent 的)。
        image = await self._image_for(agent_name)
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
        # sandbox-skill-mount: resolve before the reuse decision so the mount source/mode
        # contributes to config_hash — changing it rebuilds a reused container. A blocked
        # source raises here, before any create.
        skill_mount = self._resolve_skill_mount()
        desired_hash = config_hash(
            image, self.resources_for(scope), env, host_path, skill_mount=skill_mount
        )

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
            skill_mount=skill_mount,
        )
        self._registry[name] = _Entry(workspace_id, scope, key, now)
        return workspace_id

    async def _image_for(self, agent_name: str) -> str | None:
        """Select the boot image, decoupled from `workspace_scope`.

        Image selection is driven only by the per-agent image-persistence switch and
        the backend's `persist_workspace` capability (sandbox-image-persistence), never
        by `workspace_scope`:

        - persistence off, or backend cannot persist → base image (None).
        - persistence on + `persist_workspace` backend → the declaratively built
          *immutable* deps image when it exists (`fleetent-sandbox-deps-<key>`), else
          base image. Never queries a from-running `docker commit` product.

        For a `persist_workspace=False` backend (e.g. microsandbox, no image-commit
        primitive) hot-start is not achievable: it always returns None and logs that
        the dependency runtime is re-readied from the base image, so callers never
        mistake it for a persisted hot-start image.
        """
        if not self.image_persistence:
            return None
        if not self.backend.capabilities.persist_workspace:
            _logger.info(
                "sandbox_image_persistence_unavailable_no_hot_start",
                backend=self.backend.name,
                note="dependency runtime re-readied from base image each acquire",
            )
            return None
        tag = _deps_image_tag(agent_name)
        if await self.backend.image_exists(tag):
            return tag
        return None

    def forget(self, name: str) -> None:
        """Drop a registry entry whose container was destroyed out-of-band.

        run_code's cancel path force-destroys the container (AR19 hard abort); it
        calls this so the next acquire's `find_workspace` miss rebuilds cleanly.
        """
        self._registry.pop(name, None)

    def container_name(self, scope: WorkspaceScope, session_id: str, agent_name: str) -> str:
        """Public name resolver so callers (run_code) can forget by name on abort."""
        key = workspace_scope_key(scope, session_id, agent_name)
        return _container_name(scope, key)

    def invalidate(self, scope: WorkspaceScope, session_id: str, agent_name: str) -> None:
        """Drop the (scope, key) registration so the next acquire rebuilds.

        Called by exec-layer self-healing when a command hits a missing-container
        error after acquire (the verify-then-die race window).
        """
        key = workspace_scope_key(scope, session_id, agent_name)
        self._registry.pop(_container_name(scope, key), None)

    def workspace_host_path(self, scope: WorkspaceScope, session_id: str, agent_name: str) -> Path:
        """Return (creating) the host dir mounted at ``/workspace`` for (scope, key).

        Shared by `acquire` (the bind-mount source) and the file tools' host-degrade
        backend (the path fence root), so both agree on exactly one directory per
        scope key. Idempotent: creates the dir tree if missing.
        """
        key = workspace_scope_key(scope, session_id, agent_name)
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
        name = _container_name(WorkspaceScope.SESSION, session_id)
        entry = self._registry.get(name)
        if entry is None or entry.scope is not WorkspaceScope.SESSION:
            return
        await self.backend.destroy_workspace(entry.workspace_id)
        self._registry.pop(name, None)

    async def sweep_idle(self) -> None:
        """Reclaim `agent`-scope containers idle past `idle_hours` (pure destroy).

        Container liveness is the only thing reclaimed here: a stale container is
        destroyed directly. `docker commit`-from-running-container is retired from the
        lifecycle hot path (sandbox-image-persistence) — committing a container that
        ran end-user code would bake that user's rootfs/site-packages into the next
        boot image, and runtime `--read-only` / `--network none` are powerless over
        already-baked layers. Dependency persistence is now an independent offline
        declarative build (see `_image_for`), fully decoupled from container liveness.
        `session` scope never participates in idle reclaim.
        """
        # Imported lazily: workspace_gc imports _name_key from this module, so a
        # top-level import here would close an import cycle.
        from fleetent.integrations.sandbox import workspace_gc

        now = self.clock()
        cutoff = self.idle_hours * 3600
        stale = [
            entry
            for entry in self._registry.values()
            if entry.scope is WorkspaceScope.AGENT and (now - entry.last_used) > cutoff
        ]
        for entry in stale:
            await self.backend.destroy_workspace(entry.workspace_id)
            self._registry.pop(_container_name(entry.scope, entry.key), None)

        # sandbox-workspace-gc: prune stale entries inside every known agent-scope
        # workspace dir by mtime (the dir is cross-session shared, so it is never
        # deleted wholesale, unlike session scope). Run after reclaim so a just-swept
        # agent's dir is included. Best-effort — a prune failure must not abort sweep.
        agent_keys = {e.key for e in self._registry.values() if e.scope is WorkspaceScope.AGENT}
        agent_keys.update(e.key for e in stale)
        for key in agent_keys:
            try:
                workspace_gc.gc_agent_workspace(key)
            except OSError as exc:
                _logger.warn("sandbox_agent_workspace_gc_failed", key=key, error=str(exc))
