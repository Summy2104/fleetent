"""microsandbox-backed sandbox backend (microsandbox-backend).

Wraps the official ``microsandbox`` SDK (Apache-2.0), which runs OCI images inside
local microVMs via an embedded libkrunfw runtime — no Docker daemon, no server, no
API key (see DECISIONS.md D-spike-1, measured against microsandbox==0.5.6). The SDK
is **lazy-imported** inside each method so a deployment that selects the Docker
backend never loads it (and a missing package degrades `available()` to False rather
than crashing import).

Capability stance: `persist_workspace=False` — no image-build/commit primitive, so
declarative dependency-image hot-start (sandbox-image-persistence) is **not achievable**
on this backend. Dependencies are re-readied at runtime from the base image each
acquire; `build_deps_image` is intentionally not implemented (the base default raises)
and the manager never queries a deps image for this backend (it logs that hot-start is
not available). `workspace_mount=True` (`Volume.bind`), `orphan_cleanup=True`
(`Sandbox.list`).

Resource mapping: generic fields (memory/cpus/network/read_only) map to SDK kwargs;
Docker-only hardening fields (pids_limit/cap_*/tmpfs/etc.) are ignored — the microVM
boundary provides isolation natively. Env is injected per-exec (the SDK has no
create-time env), re-running the sensitive-name filter for defence in depth.
"""

from __future__ import annotations

from typing import Any

from fleetent.integrations.sandbox.backend import (
    BackendCapabilities,
    BaseSandboxBackend,
    ExecResult,
    SkillMount,
)
from fleetent.integrations.sandbox.config import NetworkPolicy, SandboxResources
from fleetent.integrations.sandbox.secrets import is_sensitive_name
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.microsandbox")

# Container-side mount point for the host workspace dir (mirrors the Docker backend).
_WORKSPACE_MOUNT = "/workspace"
# Skills mount point + env var (mirrors the Docker backend, sandbox-skill-mount).
_SKILLS_MOUNT = "/workspace/skills"
_SKILLS_DIR_ENV = "SKILLS_DIR"


class MicrosandboxBackend(BaseSandboxBackend):
    name = "microsandbox"
    capabilities = BackendCapabilities(
        persist_workspace=False, workspace_mount=True, orphan_cleanup=True
    )

    def __init__(self, image: str = "python:3.12-slim") -> None:
        super().__init__()
        self._image = image
        # Live sandbox handles and per-workspace filtered env, keyed by workspace name
        # (the SDK addresses sandboxes by name; env is applied per-exec, not at create).
        self._handles: dict[str, Any] = {}
        self._env: dict[str, dict[str, str]] = {}

    async def available(self) -> bool:
        """Whether the microsandbox runtime is installed and usable, never raising.

        Missing package (ImportError) or an unusable runtime / probe error degrades to
        False so the platform falls back to OFF instead of crashing at startup.
        """
        try:
            import microsandbox

            return bool(microsandbox.is_installed())
        except Exception as exc:  # noqa: BLE001 — probe must never raise (degrade to OFF)
            _logger.warn("microsandbox_probe_failed", error=str(exc))
            return False

    @staticmethod
    def _filter_env(env: dict[str, str] | None) -> dict[str, str]:
        """Defence-in-depth: drop sensitive-named vars even if the caller pre-filtered."""
        if not env:
            return {}
        return {k: v for k, v in env.items() if not is_sensitive_name(k)}

    @staticmethod
    def _map_network(policy: NetworkPolicy) -> Any:
        import microsandbox

        if policy is NetworkPolicy.ALLOW_ALL:
            return microsandbox.Network.allow_all()
        if policy is NetworkPolicy.PUBLIC_ONLY:
            return microsandbox.Network.public_only()
        return microsandbox.Network.none()

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
        """Start a microVM named `name`, returning the name as the workspace id.

        Generic resource fields map to SDK kwargs; Docker-only hardening fields are
        ignored. `workspace_host_path` becomes a `Volume.bind` at /workspace (honouring
        `read_only`). `config_hash` has no SDK equivalent (no label mechanism) and is
        accepted but unused. `skill_mount` (sandbox-skill-mount) adds a second
        `Volume.bind` at /workspace/skills and injects `SKILLS_DIR` into the per-exec
        env (platform injection wins over a sandbox_env clash). The filtered env is
        stored for per-exec injection.
        """
        import microsandbox

        if resources is None:
            resources = SandboxResources()
        create_kwargs: dict[str, Any] = {
            "image": image or self._image,
            "cpus": max(1, int(round(resources.cpus))),
            "memory": resources.memory,
            "network": self._map_network(resources.network),
        }
        volumes: dict[str, Any] = {}
        if workspace_host_path:
            volumes[_WORKSPACE_MOUNT] = microsandbox.Volume.bind(
                workspace_host_path, readonly=resources.read_only
            )
        if skill_mount is not None:
            volumes[_SKILLS_MOUNT] = microsandbox.Volume.bind(
                skill_mount.host_src, readonly=skill_mount.read_only
            )
        if volumes:
            create_kwargs["volumes"] = volumes
        handle = await microsandbox.Sandbox.create(name, **create_kwargs)
        self._handles[name] = handle
        stored_env = self._filter_env(env)
        if skill_mount is not None:
            if _SKILLS_DIR_ENV in stored_env and stored_env[_SKILLS_DIR_ENV] != _SKILLS_MOUNT:
                _logger.warn(
                    "sandbox_skills_dir_env_override",
                    supplied=stored_env[_SKILLS_DIR_ENV],
                    using=_SKILLS_MOUNT,
                )
            stored_env[_SKILLS_DIR_ENV] = _SKILLS_MOUNT
        self._env[name] = stored_env
        _logger.info("microsandbox_created", name=name)
        return name

    async def find_workspace(self, name: str) -> str | None:
        """Reconnect to a live sandbox by name via `Sandbox.get`, or None if absent."""
        import microsandbox

        try:
            handle = await microsandbox.Sandbox.get(name)
        except Exception:  # noqa: BLE001 — absent / unreachable -> not found
            return None
        self._handles[name] = handle
        return name

    async def _handle_for(self, workspace_id: str) -> Any:
        handle = self._handles.get(workspace_id)
        if handle is not None:
            return handle
        import microsandbox

        handle = await microsandbox.Sandbox.get(workspace_id)
        self._handles[workspace_id] = handle
        return handle

    async def _run_exec(
        self, workspace_id: str, command: str, stdin: bytes | None = None
    ) -> ExecResult:
        handle = await self._handle_for(workspace_id)
        output = await handle.exec(
            "sh", ["-c", command], stdin=stdin, env=self._env.get(workspace_id) or None
        )
        return ExecResult(
            stdout=output.stdout_text,
            stderr=output.stderr_text,
            exit_code=output.exit_code,
        )

    async def destroy_workspace(self, workspace_id: str) -> None:
        """Remove the sandbox by name; idempotent (a missing sandbox is not an error)."""
        import microsandbox

        try:
            await microsandbox.Sandbox.remove(workspace_id)
        except Exception as exc:  # noqa: BLE001 — already gone -> idempotent no-op
            _logger.debug("microsandbox_remove_noop", name=workspace_id, error=str(exc))
        self._handles.pop(workspace_id, None)
        self._env.pop(workspace_id, None)

    async def kill_workspace(self, workspace_id: str) -> None:
        """Forcefully stop the microVM via the SDK's native stop (no signal sequence)."""
        try:
            handle = await self._handle_for(workspace_id)
            await handle.stop()
        except Exception as exc:  # noqa: BLE001 — best-effort termination
            _logger.warn("microsandbox_stop_failed", name=workspace_id, error=str(exc))

    async def list_workspaces(self, name_prefix: str) -> list[str]:
        """Enumerate sandbox names matching `name_prefix` via `Sandbox.list`; [] on error."""
        import microsandbox

        try:
            sandboxes = await microsandbox.Sandbox.list()
        except Exception as exc:  # noqa: BLE001 — enumeration failure -> empty
            _logger.warn("microsandbox_list_failed", prefix=name_prefix, error=str(exc))
            return []
        return [sb.name for sb in sandboxes if str(getattr(sb, "name", "")).startswith(name_prefix)]
