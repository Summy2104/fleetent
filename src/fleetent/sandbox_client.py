from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

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

    async def create_workspace(self, session_id: str) -> str:
        """Start an isolated container, return container ID as workspace_id."""
        safe = _SAFE_NAME.sub("-", session_id)[:48]
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "-d",
            "--name",
            f"sandbox-{safe}",
            "--network",
            "none",
            "--memory",
            "256m",
            "--cpus",
            "0.5",
            "--read-only",
            "--tmpfs",
            "/tmp",
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
