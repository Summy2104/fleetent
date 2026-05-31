from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from fleetent.sandbox_config import NetworkPolicy, SandboxResources

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]")


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

    async def create_workspace(
        self, session_id: str, resources: SandboxResources | None = None
    ) -> str:
        """Start an isolated container, return container ID as workspace_id.

        Resource limits are taken per call from `resources` (SB2 needs one client
        to build both read-only session and writable agent containers), defaulting
        to `SandboxResources()` — byte-equivalent to the pre-SB4 hardcoded command.
        """
        if resources is None:
            resources = SandboxResources()
        safe = _SAFE_NAME.sub("-", session_id)[:48]
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "-d",
            "--name",
            f"sandbox-{safe}",
            *self._resource_flags(resources),
            self._image,
            "sleep",
            "infinity",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {stderr.decode().strip()}")
        container_id = stdout.decode().strip()
        logger.info("sandbox_created", session_id=session_id, container_id=container_id[:12])
        return container_id

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
