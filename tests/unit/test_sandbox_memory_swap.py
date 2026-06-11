"""Unit tests: 沙箱内存硬上限（--memory-swap）（sandbox-memory-hard-limit）。

直接测 staticmethod `_resource_flags` 与 config 载入，无需 docker / subprocess。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fleetent.integrations.sandbox.backends.docker as client_mod
from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.config import (
    SandboxResources,
    build_resources_by_scope,
    load_sandbox_resources,
)


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


# ── config 载入 ──────────────────────────────────────────────────────────────


def _write_yaml(path: Path, body: str) -> None:
    path.write_text(body)


def test_load_memory_swap_mb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "platform.yaml"
    _write_yaml(path, "sandbox:\n  resources:\n    memory: 256\n    memory_swap_mb: 1024\n")
    res = load_sandbox_resources(path)
    assert res.memory_swap_mb == 1024


def test_load_memory_swap_default_none(tmp_path: Path) -> None:
    path = tmp_path / "platform.yaml"
    _write_yaml(path, "sandbox:\n  resources:\n    memory: 256\n")
    res = load_sandbox_resources(path)
    assert res.memory_swap_mb is None


def test_invalid_memory_swap_falls_back_to_none(tmp_path: Path) -> None:
    path = tmp_path / "platform.yaml"
    _write_yaml(path, "sandbox:\n  resources:\n    memory_swap_mb: 0\n")
    assert load_sandbox_resources(path).memory_swap_mb is None
    _write_yaml(path, "sandbox:\n  resources:\n    memory_swap_mb: notint\n")
    assert load_sandbox_resources(path).memory_swap_mb is None


# ── build_resources_by_scope：agent_scope override + None 跟随 ─────────────────


def test_agent_scope_memory_swap_override(tmp_path: Path) -> None:
    path = tmp_path / "platform.yaml"
    _write_yaml(
        path,
        "sandbox:\n  resources:\n    memory: 256\n"
        "  agent_scope:\n    memory: 512\n    memory_swap_mb: 1024\n",
    )
    by_scope = build_resources_by_scope(path)
    agent = by_scope["agent"]
    assert agent.memory == 512
    assert agent.memory_swap_mb == 1024
    assert _swap_value(SandboxClient._resource_flags(agent)) == "1024m"


def test_agent_scope_memory_only_swap_follows(tmp_path: Path) -> None:
    """agent_scope 仅提 memory、未配 swap：None 跟随语义 → swap == 提高后的 memory。"""
    path = tmp_path / "platform.yaml"
    _write_yaml(
        path,
        "sandbox:\n  resources:\n    memory: 256\n  agent_scope:\n    memory: 1024\n",
    )
    by_scope = build_resources_by_scope(path)
    agent = by_scope["agent"]
    assert agent.memory_swap_mb is None
    assert _swap_value(SandboxClient._resource_flags(agent)) == "1024m"
