from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from fleetent.integrations.sandbox.config import NetworkPolicy, SandboxResources
from fleetent.integrations.sandbox.secrets import is_sensitive_name

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]")

# Grace window between SIGTERM and the unconditional SIGKILL of the docker-kill
# sequence (SB7). Module-level so tests inject a tiny value; no global mutable state.
_KILL_GRACE_SECONDS = 5.0

# Single source of truth for the container-name prefix. Defined here (the lowest
# layer) so SB2's naming rule and SB8's orphan enumeration share one constant
# without a circular import. SB2 builds `sandbox-{scope}-{key}` atop it.
SANDBOX_NAME_PREFIX = "sandbox-"


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int


class SandboxClient:
    def __init__(self, image: str = "python:3.12-slim") -> None:
        self._image = image

    async def docker_available(self) -> bool:
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
            logger.warning("docker_probe_failed error=%s", exc)
            return False
        if proc.returncode != 0:
            logger.warning("docker_probe_nonzero returncode=%s", proc.returncode)
            return False
        return True

    @staticmethod
    def _resource_flags(resources: SandboxResources) -> list[str]:
        """Map SandboxResources to docker run flags (D2).

        `exec_timeout` is deliberately absent — it is a per-exec timeout carried
        for wave-3 forced termination, not a `docker run` concern. `--tmpfs /tmp`
        is always present (writable scratch independent of read_only). `public_only`
        has no provisioned network here, so it degrades to `--network none` rather
        than silently allowing the default bridge.
        """
        flags = ["--memory", f"{resources.memory}m", "--cpus", str(resources.cpus)]
        if resources.network is NetworkPolicy.NONE:
            flags += ["--network", "none"]
        elif resources.network is NetworkPolicy.PUBLIC_ONLY:
            logger.warning("sandbox_public_only_network_unprovisioned falling_back_to=none")
            flags += ["--network", "none"]
        if resources.read_only:
            flags.append("--read-only")
        flags += ["--tmpfs", "/tmp"]
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

    async def create_workspace(
        self,
        name: str,
        resources: SandboxResources | None = None,
        image: str | None = None,
        env: dict[str, str] | None = None,
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
        """
        if resources is None:
            resources = SandboxResources()
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            *self._resource_flags(resources),
            *self._env_flags(env),
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
        logger.info("sandbox_created name=%s container_id=%s", name, container_id[:12])
        return container_id

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

    async def list_containers(self, name_prefix: str) -> list[str]:
        """Return names of all containers whose name matches `name_prefix` (D2).

        Runs `docker ps -a --filter name=<prefix> --format {{.Names}}`; `-a`
        includes stopped containers so orphans that already exited (but were
        never removed) are still enumerated. Like `docker_available`, this never
        raises: a missing CLI, a failed spawn, or a non-zero exit logs a warning
        and returns an empty list so SB8's startup cleanup degrades silently when
        Docker is absent. `--filter name=` is substring matching, so callers must
        re-check the prefix before destroying (D3).
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
            logger.warning("docker_list_containers_failed prefix=%s error=%s", name_prefix, exc)
            return []
        if proc.returncode != 0:
            logger.warning(
                "docker_list_containers_nonzero prefix=%s returncode=%s error=%s",
                name_prefix,
                proc.returncode,
                stderr.decode().strip(),
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
        logger.info("sandbox_committed container_id=%s tag=%s", workspace_id[:12], image_tag)

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
            logger.warning("docker_image_inspect_failed tag=%s error=%s", image_tag, exc)
            return False
        return proc.returncode == 0

    async def exec(self, workspace_id: str, command: str) -> ExecResult:
        """Execute a shell command inside the running container."""
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            workspace_id,
            "sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
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
        logger.info("sandbox_destroyed", container_id=workspace_id[:12])

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
            logger.warning(
                "docker_kill_nonzero signal=%s container_id=%s returncode=%s",
                signal,
                workspace_id[:12],
                proc.returncode,
            )
