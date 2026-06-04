"""Tests for sandbox resource configuration (SB4: load + defaults + validation)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from fleetent.integrations.sandbox import config as sandbox_config
from fleetent.integrations.sandbox.config import (
    NetworkPolicy,
    SandboxResources,
    load_sandbox_resources,
)


def test_network_policy_members() -> None:
    assert NetworkPolicy.NONE == "none"
    assert NetworkPolicy.PUBLIC_ONLY == "public_only"
    assert NetworkPolicy.ALLOW_ALL == "allow_all"


def test_sandbox_resources_safe_defaults() -> None:
    res = SandboxResources()
    assert res.memory == 256
    assert res.cpus == 0.5
    assert res.network is NetworkPolicy.NONE
    assert res.exec_timeout == 30
    assert res.read_only is True


def _write_settings(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(textwrap.dedent(body))
    return path


def test_load_overrides_all_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          mode: all
          resources:
            memory: 1024
            cpus: 2.0
            network: allow_all
            exec_timeout: 120
            read_only: false
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    res = load_sandbox_resources()
    assert res.memory == 1024
    assert res.cpus == 2.0
    assert res.network is NetworkPolicy.ALLOW_ALL
    assert res.exec_timeout == 120
    assert res.read_only is False


def test_load_missing_fields_fall_back_per_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            memory: 512
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    res = load_sandbox_resources()
    assert res.memory == 512
    assert res.cpus == 0.5
    assert res.network is NetworkPolicy.NONE
    assert res.exec_timeout == 30
    assert res.read_only is True


def test_load_missing_file_returns_all_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", tmp_path / "absent.yaml")
    assert load_sandbox_resources() == SandboxResources()


def test_load_no_sandbox_section_returns_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(tmp_path, "log_format: console\n")
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    assert load_sandbox_resources() == SandboxResources()


def test_load_accepts_explicit_path_argument(tmp_path: Path) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            memory: 768
        """,
    )
    res = load_sandbox_resources(path)
    assert res.memory == 768


def test_invalid_memory_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            memory: 0
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    res = load_sandbox_resources()
    assert res.memory == 256


def test_invalid_cpus_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            cpus: -1
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    res = load_sandbox_resources()
    assert res.cpus == 0.5


def test_invalid_network_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            network: lan_only
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    res = load_sandbox_resources()
    assert res.network is NetworkPolicy.NONE


def test_exec_timeout_below_floor_clamped_to_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            exec_timeout: 0
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    assert load_sandbox_resources().exec_timeout == 1


def test_exec_timeout_above_ceiling_clamped_to_600(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            exec_timeout: 1000
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    assert load_sandbox_resources().exec_timeout == 600


def test_exec_timeout_within_range_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            exec_timeout: 45
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    assert load_sandbox_resources().exec_timeout == 45


# --- SB2 lifecycle config (scope / idle_hours) -----------------------------


def test_load_lifecycle_defaults_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.integrations.sandbox.config import load_sandbox_lifecycle

    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", tmp_path / "absent.yaml")
    lc = load_sandbox_lifecycle()
    assert lc.scope == "session"
    assert lc.idle_hours == 2.0


def test_load_lifecycle_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.integrations.sandbox.config import load_sandbox_lifecycle

    path = _write_settings(
        tmp_path,
        """
        sandbox:
          scope: agent
          idle_hours: 6
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    lc = load_sandbox_lifecycle()
    assert lc.scope == "agent"
    assert lc.idle_hours == 6.0


def test_load_lifecycle_invalid_scope_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.integrations.sandbox.config import load_sandbox_lifecycle

    path = _write_settings(
        tmp_path,
        """
        sandbox:
          scope: bogus
          idle_hours: -1
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    lc = load_sandbox_lifecycle()
    assert lc.scope == "session"
    assert lc.idle_hours == 2.0


# --- SB2 scope→tier mapping (consumes SB4 resources + agent_scope override) -


def test_build_resources_by_scope_session_hardened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.integrations.sandbox.config import build_resources_by_scope

    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", tmp_path / "absent.yaml")
    by_scope = build_resources_by_scope()
    assert by_scope["session"].read_only is True
    assert by_scope["session"].network is NetworkPolicy.NONE


def test_build_resources_by_scope_agent_downgraded_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no agent_scope override, agent tier still drops read_only to writable."""
    from fleetent.integrations.sandbox.config import build_resources_by_scope

    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", tmp_path / "absent.yaml")
    by_scope = build_resources_by_scope()
    assert by_scope["agent"].read_only is False


def test_build_resources_by_scope_agent_scope_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.integrations.sandbox.config import build_resources_by_scope

    path = _write_settings(
        tmp_path,
        """
        sandbox:
          resources:
            memory: 512
          agent_scope:
            network: allow_all
            memory: 2048
        """,
    )
    monkeypatch.setattr(sandbox_config, "SETTINGS_PATH", path)
    by_scope = build_resources_by_scope()
    # session keeps base resources hardened
    assert by_scope["session"].memory == 512
    assert by_scope["session"].read_only is True
    # agent inherits base then applies override + forced writable rootfs
    assert by_scope["agent"].memory == 2048
    assert by_scope["agent"].network is NetworkPolicy.ALLOW_ALL
    assert by_scope["agent"].read_only is False
