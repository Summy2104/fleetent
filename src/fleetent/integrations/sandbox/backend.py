"""Pluggable sandbox backend abstraction (sandbox-backend-abstraction).

The backend abstraction is the single seam every code-execution backend implements:
Docker today, microsandbox alongside it. The core surface (`available` /
`create_workspace` / `find_workspace` / `exec` / `destroy_workspace` /
`kill_workspace`) is mandatory; the capability-gated surface (`commit_workspace` /
`image_exists` / `list_workspaces` / `inspect_config_hash`) is only meaningful on
backends that declare the matching `BackendCapabilities` flag — callers gate on the
capability rather than the concrete type (no isinstance).

The session-snapshot continuity logic (env/cwd persisted across `exec` calls) is
backend-agnostic, so it lives here as a template method (`exec`) driving a subclass's
`_run_exec` primitive. Both backends share it verbatim; only the primitive differs.
"""

from __future__ import annotations

import re
import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from fleetent.integrations.sandbox.config import SandboxResources
from fleetent.integrations.sandbox.session_snapshot import (
    DEFAULT_CWD,
    build_capture_script,
    extract_cwd,
    wrap_command,
)

# Single source of truth for the workspace-name prefix, shared by the manager's
# naming rule (`sandbox-{scope}-{key}`) and orphan enumeration. Defined here (the
# lowest layer) so neither side reaches into a concrete backend for it.
SANDBOX_NAME_PREFIX = "sandbox-"

# Shared workspace-name sanitiser: backend-agnostic naming policy used by the
# manager to build `sandbox-{scope}-{key}` names. Lives here (not in a concrete
# backend) so every backend and the manager agree on one rule.
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]")


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True)
class SkillMount:
    """A host skills directory to bind-mount into the container at /workspace/skills.

    `host_src` is the already-resolved host skills root (the manager validates it
    against `is_blocked_mount` before constructing this). `read_only` defaults to
    True: skill assets are author/operator-maintained and the agent runtime should
    not rewrite them; an operator can flip it to allow in-container writes. Frozen so
    a mount spec threaded through acquire→create_workspace is an immutable contract
    and can contribute stably to `config_hash`.
    """

    host_src: str
    read_only: bool = True


@dataclass(frozen=True)
class BackendCapabilities:
    """What a backend can do beyond the mandatory core surface.

    Callers gate optional behaviour on these flags so a backend that cannot
    persist dependencies / bind-mount a host dir / enumerate leftovers degrades
    gracefully instead of erroring. Frozen so a backend's declared capabilities
    are an immutable contract.
    """

    persist_workspace: bool
    workspace_mount: bool
    orphan_cleanup: bool


class BaseSandboxBackend(ABC):
    """Abstract base every sandbox backend extends.

    Subclasses set the `name` / `capabilities` class attributes and implement the
    core surface plus the `_run_exec` primitive; the session-snapshot continuity
    template (`exec`) is inherited unchanged. `__init__` owns the per-session
    snapshot state so it is instance-scoped (no module-global mutable state).
    """

    name: ClassVar[str]
    capabilities: ClassVar[BackendCapabilities]

    def __init__(self) -> None:
        # Which sessions have captured their env, and each session's persisted cwd.
        self._snap_ready: set[str] = set()
        self._cwd: dict[str, str] = {}

    # ── mandatory core surface ────────────────────────────────────────────────

    @abstractmethod
    async def available(self) -> bool:
        """Probe whether this backend is usable, never raising (degrades to OFF)."""

    @abstractmethod
    async def create_workspace(
        self,
        name: str,
        resources: SandboxResources | None = None,
        image: str | None = None,
        env: dict[str, str] | None = None,
        workspace_host_path: str | None = None,
        config_hash: str | None = None,
        skill_mount: SkillMount | None = None,
    ) -> str:
        """Start an isolated workspace under `name`, returning its workspace id.

        `skill_mount` (sandbox-skill-mount) optionally bind-mounts a host skills root
        at /workspace/skills and injects `SKILLS_DIR`; None keeps the prior behaviour
        (backward compatible) and is ignored by backends without `workspace_mount`.
        """

    @abstractmethod
    async def find_workspace(self, name: str) -> str | None:
        """Return the id of a live workspace named `name`, or None if absent."""

    @abstractmethod
    async def destroy_workspace(self, workspace_id: str) -> None:
        """Stop and remove the workspace; MUST be idempotent."""

    @abstractmethod
    async def kill_workspace(self, workspace_id: str) -> None:
        """Forcefully terminate the workspace's process(es)."""

    @abstractmethod
    async def _run_exec(
        self, workspace_id: str, command: str, stdin: bytes | None = None
    ) -> ExecResult:
        """Run a single shell command in the workspace via the backend's primitive.

        Receives a shell command string (the continuity template builds the
        `bash -lc` / `bash -c` wrappers); the backend runs it through its own
        `sh -c` channel and returns the raw result.
        """

    # ── capability-gated surface (safe defaults for backends without it) ──────

    async def commit_workspace(self, workspace_id: str, image_tag: str) -> None:
        """Persist a workspace's deps into an image (persist_workspace backends)."""
        raise NotImplementedError(f"{self.name} backend does not support commit_workspace")

    async def image_exists(self, image_tag: str) -> bool:
        """Whether a committed dependency image exists (persist_workspace backends)."""
        return False

    async def list_workspaces(self, name_prefix: str) -> list[str]:
        """Enumerate workspace names by prefix (orphan_cleanup backends); else []."""
        return []

    async def inspect_config_hash(self, name: str) -> str | None:
        """Read a workspace's stamped config-hash; None means 'conservatively reuse'."""
        return None

    def is_workspace_missing(self, result: ExecResult) -> bool:
        """Classify an exec result as a container-missing infrastructure failure.

        Lets the exec layer self-heal (deregister + re-acquire) instead of surfacing
        a dead container as a tool-level "path not found". Backends override with
        their own error signatures; the base default never claims missing.
        """
        return False

    # ── session-snapshot continuity template (shared by all backends) ─────────

    async def exec(
        self,
        workspace_id: str,
        command: str,
        session_id: str | None = None,
        stdin: bytes | None = None,
    ) -> ExecResult:
        """Execute a shell command, with session-snapshot continuity when asked.

        ``session_id=None`` runs the command verbatim. Otherwise env/cwd persist
        across calls via a captured-then-restored snapshot (sandbox-session-snapshot);
        a capture failure degrades to a login shell so the command still runs,
        only losing cross-exec continuity. ``stdin`` is piped to the command.
        """
        if session_id is None:
            return await self._run_exec(workspace_id, command, stdin=stdin)
        if session_id not in self._snap_ready:
            capture = build_capture_script(session_id)
            cap_res = await self._run_exec(workspace_id, f"bash -lc {shlex.quote(capture)}")
            if cap_res.exit_code == 0:
                self._snap_ready.add(session_id)
        if session_id not in self._snap_ready:
            return await self._run_exec(
                workspace_id, f"bash -lc {shlex.quote(command)}", stdin=stdin
            )
        cwd = self._cwd.get(session_id, DEFAULT_CWD)
        wrapped = wrap_command(command, session_id, cwd)
        result = await self._run_exec(workspace_id, f"bash -c {shlex.quote(wrapped)}", stdin=stdin)
        new_cwd, cleaned = extract_cwd(result.stdout, session_id)
        if new_cwd:
            self._cwd[session_id] = new_cwd
        return ExecResult(stdout=cleaned, stderr=result.stderr, exit_code=result.exit_code)
