"""Shell execution tool: bash_exec.

Runs arbitrary shell commands on the host (NOT sandboxed). Distinct from
run_code (Docker-isolated Python). Use for DevOps/ops tasks where direct
host access is needed and the user has approved via permission_gate (risk=high).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fleetent.runtime.cancellation import CancelToken
from fleetent.tools.registry import ToolContext, tool

logger = logging.getLogger(__name__)

_CANCEL_POLL = 0.05  # seconds between cancellation checks


@tool(risk_level="high", self_truncates=True)
async def bash_exec(
    command: Annotated[str, "要执行的 Shell 命令"],
    description: Annotated[str, "命令意图的简短描述（5-10 词，用于权限审查展示）"],
    workdir: Annotated[str, "工作目录（可选，默认继承当前目录）"] = "",
    timeout: Annotated[float, "超时秒数（默认 120.0）"] = 120.0,
    cancel_token: CancelToken | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """在宿主机执行 Shell；看不到 /workspace 与会话文件，处理会话文件请用容器内工具 run_code。

    Returns combined stdout + stderr output. Non-zero exit codes are appended
    as [exit N]. Large output uses the spillover strategy. Supports cancellation
    via CancelToken and configurable timeout. Requires approval (risk=high). Use this
    for host/DevOps operations only; uploads, generated images and skill resources live
    under /workspace and are reachable from run_code, not from bash_exec.
    """
    cwd = workdir if workdir else None
    token = cancel_token if cancel_token is not None else CancelToken()

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except OSError as exc:
        return f"error: 无法启动命令: {exc}"

    async def _wait() -> tuple[bytes, bytes, int]:
        stdout, stderr = await proc.communicate()
        return stdout, stderr, proc.returncode or 0

    wait_task = asyncio.create_task(_wait())
    deadline = asyncio.get_event_loop().time() + timeout
    timed_out = False
    cancelled = False

    while True:
        done, _ = await asyncio.wait({wait_task}, timeout=_CANCEL_POLL)
        if wait_task in done:
            break

        if token.is_cancelled():
            cancelled = True
            break

        if asyncio.get_event_loop().time() >= deadline:
            timed_out = True
            break

    if timed_out or cancelled:
        wait_task.cancel()
        with __import__("contextlib").suppress(Exception):
            proc.kill()
        await asyncio.gather(wait_task, return_exceptions=True)
        if timed_out:
            return f"bash_exec 执行超时（{timeout}s），命令已终止"
        return "执行已取消"

    stdout_bytes, stderr_bytes, exit_code = wait_task.result()

    parts: list[str] = []
    stdout = stdout_bytes.decode("utf-8", errors="replace").rstrip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").rstrip()

    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    if exit_code != 0:
        parts.append(f"[exit {exit_code}]")

    raw = "\n".join(parts) if parts else "(no output)"

    # Apply spillover truncation (self_truncates=True means registry won't
    # double-truncate, but we explicitly call with self_truncates=True so the
    # legacy head+tail path is used — preserving stdout start for debugging).
    from fleetent.tools.result_truncation import truncate_tool_result

    return truncate_tool_result(raw, self_truncates=True)
