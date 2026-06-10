"""Integration test: 默认禁 swap 下内存为硬 RAM 上限（真实 docker）。

main 基线（仅 --memory、Docker 默认 2x swap）下，256m 限制可分配 ~400MB；本变更
默认 --memory-swap == --memory 后，超 memory 的分配应被 OOM 终止。docker 不可用时跳过。
"""

from __future__ import annotations

import subprocess

import pytest

from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.config import SandboxResources


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "version"], capture_output=True).returncode == 0
    except (FileNotFoundError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="docker not available")


async def test_default_memory_limit_is_hard_rss_cap() -> None:
    """默认资源（memory=256, 禁 swap）：常驻分配 400MB 被 OOM 杀（退出码非 0）。"""
    client = SandboxClient()
    name = "sandbox-itest-memswap"
    await client.destroy_workspace(name)  # 幂等清理可能的残留
    ws = await client.create_workspace(name=name, resources=SandboxResources())
    try:
        result = await client.exec(ws, 'python3 -c "x=bytearray(400*1024*1024); print(len(x))"')
        assert result.exit_code != 0  # 禁 swap 后 400MB > 256m 硬上限 → OOM
        assert "419430400" not in result.stdout
    finally:
        await client.destroy_workspace(name)
