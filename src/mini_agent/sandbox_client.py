from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int


class SandboxClient:
    def __init__(self, base_url: str = "http://host.docker.internal:7777") -> None:
        self._base_url = base_url.rstrip("/")

    async def create_workspace(self, session_id: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/workspace",
                json={"session_id": session_id},
                timeout=30.0,
            )
            resp.raise_for_status()
            return str(resp.json()["id"])

    async def exec(self, workspace_id: str, command: str) -> ExecResult:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/workspace/{workspace_id}/exec",
                json={"command": command},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
        return ExecResult(
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", 0),
        )

    async def destroy_workspace(self, workspace_id: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self._base_url}/workspace/{workspace_id}",
                timeout=10.0,
            )
            resp.raise_for_status()
