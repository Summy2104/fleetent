"""Unit tests: 沙箱内存硬上限（--memory-swap）（sandbox-memory-hard-limit）。

直接测 staticmethod `_resource_flags` 与 config 载入，无需 docker / subprocess。
"""

from __future__ import annotations

import pytest

import fleetent.integrations.sandbox.backends.docker as client_mod
from fleetent.agent_config import SandboxResourcesSettings
from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.config import (
    SandboxResources,
    resources_from_agent_settings,
)


def _build(**fields) -> SandboxResources:
    return resources_from_agent_settings(SandboxResourcesSettings(**fields))


def _swap_value(flags: list[str]) -> str:
    return flags[flags.index("--memory-swap") + 1]


# ── _resource_flags：--memory-swap 生成 ───────────────────────────────────────


def test_default_swap_equals_memory() -> None:
    """默认（memory_swap_mb=None）：--memory-swap 等于 --memory，禁 swap。"""
    flags = SandboxClient._resource_flags(SandboxResources())
    assert _swap_value(flags) == "256m"
    assert flags[flags.index("--memory") + 1] == "256m"


def test_swap_follows_custom_memory_when_unset() -> None:
    """未配 memory_swap_mb 时，swap 跟随 memory。"""
    flags = SandboxClient._resource_flags(SandboxResources(memory=512))
    assert _swap_value(flags) == "512m"


def test_explicit_swap_total() -> None:
    """显式 memory_swap_mb：作为 memory+swap 总额。"""
    flags = SandboxClient._resource_flags(SandboxResources(memory=256, memory_swap_mb=512))
    assert _swap_value(flags) == "512m"


class _FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple] = []

    def warn(self, *a, **k) -> None:
        self.warnings.append((a, k))

    def info(self, *a, **k) -> None:  # pragma: no cover - 接口齐备
        pass


def test_swap_below_memory_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    """memory_swap_mb < memory：钳制为 memory（Docker 要求 swap≥memory），并 log warn。"""
    fake = _FakeLogger()
    monkeypatch.setattr(client_mod, "_logger", fake)

    flags = SandboxClient._resource_flags(SandboxResources(memory=512, memory_swap_mb=256))
    assert _swap_value(flags) == "512m"
    assert fake.warnings, "clamp 生效时应记录 warning"


def test_swap_equal_to_memory_no_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """memory_swap_mb == memory：不算钳制，不 warn。"""
    fake = _FakeLogger()
    monkeypatch.setattr(client_mod, "_logger", fake)

    flags = SandboxClient._resource_flags(SandboxResources(memory=256, memory_swap_mb=256))
    assert _swap_value(flags) == "256m"
    assert not fake.warnings


# ── 从 agent.yaml sandbox.resources 构建（per-agent-sandbox-resources）─────────


def test_build_memory_swap_mb() -> None:
    assert _build(memory=256, memory_swap_mb=1024).memory_swap_mb == 1024


def test_build_memory_swap_default_none() -> None:
    assert _build(memory=256).memory_swap_mb is None


def test_invalid_memory_swap_falls_back_to_none() -> None:
    assert _build(memory_swap_mb=0).memory_swap_mb is None


def test_per_agent_memory_swap_drives_flags() -> None:
    """A per-agent resources profile with explicit memory_swap_mb drives --memory-swap."""
    res = _build(memory=512, memory_swap_mb=1024)
    assert _swap_value(SandboxClient._resource_flags(res)) == "1024m"
