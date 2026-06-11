"""Docker-backed sandbox backend (sandbox-backend-abstraction).

The original `SandboxClient` implementation, migrated under the backend abstraction
as `DockerBackend`. Behaviour is unchanged: every method renders/issues the same
`docker` CLI commands as before. The only structural shifts are that `ExecResult`,
`SANDBOX_NAME_PREFIX`, `_SAFE_NAME` and the session-snapshot continuity template now
live on the shared base (`backend.py`), and `docker_available()` is renamed to the
backend-neutral `available()`. `client.py` re-exports `DockerBackend` as
`SandboxClient` so legacy imports keep working.
"""

from __future__ import annotations

import asyncio

from fleetent.integrations.sandbox.backend import (
    BackendCapabilities,
    BaseSandboxBackend,
    ExecResult,
    SkillMount,
)
from fleetent.integrations.sandbox.config import NetworkPolicy, SandboxResources
from fleetent.integrations.sandbox.secrets import is_sensitive_name
from fleetent.structured_logging import get_logger

_logger = get_logger("sandbox.docker")

# Grace window between SIGTERM and the unconditional SIGKILL of the docker-kill
# sequence (SB7). Module-level so tests inject a tiny value; no global mutable state.
_KILL_GRACE_SECONDS = 5.0

# Container-side mount point for the per-scope host workspace directory
# (sandbox-workspace-mount). The host path is the caller/manager's responsibility.
_WORKSPACE_MOUNT = "/workspace"

# Container-side mount point + env var for the host skills root (sandbox-skill-mount).
# Fixed so skill scripts locate their resources via `$SKILLS_DIR` regardless of the
# host layout; lives under /workspace so it shares the single-root world the model sees.
_SKILLS_MOUNT = "/workspace/skills"
_SKILLS_DIR_ENV = "SKILLS_DIR"


class DockerBackend(BaseSandboxBackend):
    name = "docker"
    capabilities = BackendCapabilities(
        persist_workspace=True, workspace_mount=True, orphan_cleanup=True
    )

    def __init__(self, image: str = "python:3.12-slim") -> None:
        super().__init__()
        self._image = image

    async def available(self) -> bool:
        """Probe whether the Docker CLI is usable (D2), never raising.

        Runs a lightweight `docker version` and inspects only the return code. A
        missing CLI (FileNotFoundError) or any non-zero / failed probe logs a
        warning and returns False so the platform degrades to OFF instead of
        crashing at startup.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        except (FileNotFoundError, OSError) as exc:
            _logger.warn("docker_probe_failed", error=str(exc))
            return False
        if proc.returncode != 0:
            _logger.warn("docker_probe_nonzero", returncode=proc.returncode)
            return False
        return True

    @staticmethod
    def _resource_flags(resources: SandboxResources) -> list[str]:
        """Map SandboxResources to docker run flags (D2 + container hardening).

        `exec_timeout` is deliberately absent — it is a per-exec timeout carried
        for wave-3 forced termination, not a `docker run` concern. `public_only`
        has no provisioned network here, so it degrades to `--network none` rather
        than silently allowing the default bridge.

        Container hardening (sandbox-container-hardening): `--pids-limit` caps the
        process table (fork-bomb guard); `/tmp` is bounded + `nosuid` so a RAM-backed
        tmpfs cannot exhaust host memory and cannot hold setuid binaries; `--cap-drop
        ALL` (+ minimal `--cap-add` on the agent tier) and `--security-opt
        no-new-privileges` shrink the capability surface; `--init` reaps zombies;
        `--user` runs the session tier as a non-root uid. Each is gated by its field
        so an operator can disable any of them.

        Memory hard limit (sandbox-memory-hard-limit): `--memory-swap` is always set so
        the memory cap is not silently relaxed by Docker's default 2x swap. `None`
        disables swap (`--memory-swap == --memory`, a hard RAM cap); a configured total
        is clamped to ``>= memory`` (Docker rejects a smaller swap total) with a warning,
        so no config combination can fail `docker run`.
        """
        flags = ["--memory", f"{resources.memory}m", "--cpus", str(resources.cpus)]
        swap = resources.memory if resources.memory_swap_mb is None else resources.memory_swap_mb
        if swap < resources.memory:
            _logger.warn(
                "sandbox_memory_swap_below_memory_clamped",
                memory_swap_mb=resources.memory_swap_mb,
                memory=resources.memory,
            )
            swap = resources.memory
        flags += ["--memory-swap", f"{swap}m"]
        if resources.pids_limit:
            flags += ["--pids-limit", str(resources.pids_limit)]
        if resources.cap_drop_all:
            flags += ["--cap-drop", "ALL"]
        for cap in resources.cap_add:
            flags += ["--cap-add", cap]
        if resources.no_new_privileges:
            flags += ["--security-opt", "no-new-privileges"]
        if resources.init:
            flags.append("--init")
        if resources.run_as_user:
            flags += ["--user", resources.run_as_user]
        if resources.network is NetworkPolicy.NONE:
            flags += ["--network", "none"]
        elif resources.network is NetworkPolicy.PUBLIC_ONLY:
            _logger.warn("sandbox_public_only_network_unprovisioned", falling_back_to="none")
            flags += ["--network", "none"]
        if resources.read_only:
            flags.append("--read-only")
        flags += ["--tmpfs", f"/tmp:rw,nosuid,size={resources.tmpfs_size_mb}m"]
        return flags

    @staticmethod
    def _env_flags(env: dict[str, str] | None) -> list[str]:
        """Map an env mapping to `-e KEY=VALUE` flags with a defensive filter.

        The caller is expected to pass a `build_sandbox_env` output (already
        filtered), but SB5 D3 demands defence-in-depth: re-run `is_sensitive_name`
        here so a sensitive-named var never reaches the container even if the
        caller errs. None/empty yields no flags (current behaviour).
        """
        if not env:
            return []
        flags: list[str] = []
        for key, value in env.items():
            if is_sensitive_name(key):
                continue
            flags += ["-e", f"{key}={value}"]
        return flags

    @staticmethod
    def _workspace_flags(workspace_host_path: str | None) -> list[str]:
        """Bind-mount the host workspace dir into the container at /workspace.

        None keeps the current no-mount behaviour (sandbox-workspace-mount)."""
        if not workspace_host_path:
            return []
        return ["-v", f"{workspace_host_path}:{_WORKSPACE_MOUNT}"]

    @staticmethod
    def _skill_mount_flags(skill_mount: SkillMount | None) -> list[str]:
        """Bind-mount the host skills root into the container at /workspace/skills.

        Default read_only adds the `:ro` suffix so the agent runtime cannot rewrite
        author/operator-maintained skill assets; read_only=False drops it. None keeps
        the no-mount behaviour (backward compatible / unsupported backend)."""
        if skill_mount is None:
            return []
        spec = f"{skill_mount.host_src}:{_SKILLS_MOUNT}"
        if skill_mount.read_only:
            spec += ":ro"
        return ["-v", spec]

    @staticmethod
    def _skills_env(skill_mount: SkillMount | None) -> dict[str, str]:
        """Return the SKILLS_DIR env mapping for a skill mount (empty when None)."""
        if skill_mount is None:
            return {}
        return {_SKILLS_DIR_ENV: _SKILLS_MOUNT}

    @staticmethod
    def _merge_skills_env(
        env: dict[str, str] | None, skill_mount: SkillMount | None
    ) -> dict[str, str]:
        """Overlay the platform SKILLS_DIR injection on top of `sandbox_env`.

        Platform injection wins (sandbox-skill-mount): a `sandbox_env`-supplied
        SKILLS_DIR is overridden by `/workspace/skills` and the conflict is logged, so
        an agent cannot redirect the skills root out from under the mount."""
        merged = dict(env or {})
        skills = DockerBackend._skills_env(skill_mount)
        if skills and _SKILLS_DIR_ENV in merged and merged[_SKILLS_DIR_ENV] != _SKILLS_MOUNT:
            _logger.warn(
                "sandbox_skills_dir_env_override",
                supplied=merged[_SKILLS_DIR_ENV],
                using=_SKILLS_MOUNT,
            )
        merged.update(skills)
        return merged

    @staticmethod
    def _label_flags(config_hash: str | None) -> list[str]:
        """Stamp the container with its config-hash so reuse can detect stale config."""
        if not config_hash:
            return []
        return ["--label", f"fleetent.confighash={config_hash}"]

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
        """Start an isolated container, return container ID as workspace_id.

        `name` is used verbatim as the container name — name derivation (scope
        prefix + sanitisation) is the caller/manager's responsibility under the
        converged signature. `resources` carries the per-call resource tier (SB2
        builds read-only session and writable agent containers from one client),
        defaulting to `SandboxResources()`. `image` overrides the base image so
        agent scope can boot from a committed dependency image; None keeps the
        client's default base image. `env` carries already-filtered non-sensitive
        variables to inject as `-e` (SB5); None/empty keeps the clean environment.
        `workspace_host_path` bind-mounts a host directory at /workspace
        (sandbox-workspace-mount); None keeps the container with no host mount.
        `config_hash` (sandbox-hardening) stamps a label so a later reuse can
        rebuild on config change; None omits the label. `skill_mount`
        (sandbox-skill-mount) bind-mounts the host skills root at /workspace/skills
        and injects `SKILLS_DIR`; None keeps the prior no-skills behaviour.
        """
        if resources is None:
            resources = SandboxResources()
        effective_env = self._merge_skills_env(env, skill_mount)
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            *self._resource_flags(resources),
            *self._env_flags(effective_env),
            *self._workspace_flags(workspace_host_path),
            *self._skill_mount_flags(skill_mount),
            *self._label_flags(config_hash),
            image or self._image,
            "sleep",
            "infinity",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {stderr.decode().strip()}")
        container_id = stdout.decode().strip()
        _logger.info("sandbox_created", name=name, container_id=container_id[:12])
        return container_id

    async def inspect_config_hash(self, name: str) -> str | None:
        """Read a container's ``fleetent.confighash`` label, or None when absent.

        Used by the manager to decide whether a reused container was created under a
        now-stale config. Docker prints an empty line for an unset label.
        """
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "-f",
            '{{index .Config.Labels "fleetent.confighash"}}',
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        value = stdout.decode().strip()
        return value or None

    # docker daemon error signatures meaning the exec target is gone/stopped —
    # an infrastructure failure, never a property of the path being operated on.
    _MISSING_MARKERS = ("No such container", "is not running", "No such exec instance")

    def is_workspace_missing(self, result: ExecResult) -> bool:
        return result.exit_code != 0 and any(m in result.stderr for m in self._MISSING_MARKERS)

    async def find_workspace(self, name: str) -> str | None:
        """Return the id of a running container named `name`, or None if absent.

        Used by SB2 to reuse an existing scope container before creating a new
        one. Filters by exact name; an empty `docker ps -q` output means no match.
        """
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "-q",
            "--filter",
            f"name=^{name}$",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        container_id = stdout.decode().strip()
        return container_id or None

    async def list_workspaces(self, name_prefix: str) -> list[str]:
        """Return names of all containers whose name matches `name_prefix` (D2).

        Runs `docker ps -a --filter name=<prefix> --format {{.Names}}`; `-a`
        includes stopped containers so orphans that already exited (but were
        never removed) are still enumerated. Like `available`, this never raises:
        a missing CLI, a failed spawn, or a non-zero exit logs a warning and
        returns an empty list so orphan cleanup degrades silently when Docker is
        absent. `--filter name=` is substring matching, so callers must re-check
        the prefix before destroying (D3).
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={name_prefix}",
                "--format",
                "{{.Names}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except (FileNotFoundError, OSError) as exc:
            _logger.warn("docker_list_containers_failed", prefix=name_prefix, error=str(exc))
            return []
        if proc.returncode != 0:
            _logger.warn(
                "docker_list_containers_nonzero",
                prefix=name_prefix,
                returncode=proc.returncode,
                error=stderr.decode().strip(),
            )
            return []
        return [line for line in stdout.decode().splitlines() if line.strip()]

    async def commit_workspace(self, workspace_id: str, image_tag: str) -> None:
        """Commit a container to an image so its installed deps survive a destroy.

        SB2 calls this on agent-scope containers before idle destroy so the next
        acquire can boot from the committed image instead of reinstalling. Raises
        on a non-zero commit so the caller does not destroy under the false belief
        that dependencies were captured.
        """
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "commit",
            workspace_id,
            image_tag,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"docker commit failed: {stderr.decode().strip()}")
        _logger.info("sandbox_committed", container_id=workspace_id[:12], tag=image_tag)

    async def image_exists(self, image_tag: str) -> bool:
        """Return whether a local image with `image_tag` exists (never raising).

        SB2 uses this to decide whether an agent-scope acquire can boot from a
        previously committed dependency image or must fall back to the default
        base image. `docker image inspect` exits non-zero when absent.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "image",
                "inspect",
                image_tag,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        except (FileNotFoundError, OSError) as exc:
            _logger.warn("docker_image_inspect_failed", tag=image_tag, error=str(exc))
            return False
        return proc.returncode == 0

    async def _run_exec(
        self, workspace_id: str, command: str, stdin: bytes | None = None
    ) -> ExecResult:
        # `-i` keeps stdin open so a piped write payload reaches the command; omitted
        # otherwise so non-stdin execs behave exactly as before.
        exec_args = ["docker", "exec"]
        if stdin is not None:
            exec_args.append("-i")
        exec_args += [workspace_id, "sh", "-c", command]
        proc = await asyncio.create_subprocess_exec(
            *exec_args,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=stdin)
        return ExecResult(
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            exit_code=proc.returncode or 0,
        )

    async def destroy_workspace(self, workspace_id: str) -> None:
        """Stop and remove the container; idempotent (AR19 D3b).

        `docker rm -f` on an already-removed container exits non-zero; this
        method deliberately ignores the return code so a repeat destroy — the
        cancel path's forced `rm -f` followed by `run_code`'s `finally` fallback
        — never raises on the second call.
        """
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            workspace_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        _logger.info("sandbox_destroyed", container_id=workspace_id[:12])

    async def kill_workspace(self, workspace_id: str) -> None:
        """Forcefully terminate a container: SIGTERM, fixed grace, then SIGKILL (SB7).

        The graceful two-stage sequence (sandbox.md: "SIGTERM, 5s then SIGKILL")
        gives the container's process a chance to exit cleanly. The grace window
        is a fixed wait with NO `docker inspect` polling; the trailing SIGKILL is
        unconditional (harmless/idempotent on an already-stopped container). This
        only stops the process — container removal stays with SB2's lifecycle.
        """
        await self._docker_kill(workspace_id, "SIGTERM")
        await asyncio.sleep(_KILL_GRACE_SECONDS)
        await self._docker_kill(workspace_id, "SIGKILL")

    async def _docker_kill(self, workspace_id: str, signal: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "kill",
            f"--signal={signal}",
            workspace_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        if proc.returncode not in (0, None):
            # Best-effort: a nonzero code (e.g. SIGKILL on an already-stopped
            # container) must not crash the timeout path. Log and move on.
            _logger.warn(
                "docker_kill_nonzero",
                signal=signal,
                container_id=workspace_id[:12],
                returncode=proc.returncode,
            )
