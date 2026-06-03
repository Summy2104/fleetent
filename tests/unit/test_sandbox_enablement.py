"""Tests for the three-state code-execution enablement decision (SB3)."""

from __future__ import annotations

import pytest

from fleetent.sandbox_enablement import (
    Mode,
    is_code_execution_enabled,
    resolve_effective_mode,
)


def test_mode_members_and_default():
    assert Mode.OFF == "off"
    assert Mode.SELECTIVE == "selective"
    assert Mode.ALL == "all"


@pytest.mark.parametrize("code_execution", [True, False, None])
def test_off_always_disabled(code_execution):
    assert is_code_execution_enabled(Mode.OFF, code_execution) is False


def test_selective_only_explicit_true_enabled():
    assert is_code_execution_enabled(Mode.SELECTIVE, True) is True
    assert is_code_execution_enabled(Mode.SELECTIVE, False) is False
    assert is_code_execution_enabled(Mode.SELECTIVE, None) is False


def test_all_enabled_unless_explicit_false():
    assert is_code_execution_enabled(Mode.ALL, None) is True
    assert is_code_execution_enabled(Mode.ALL, True) is True
    assert is_code_execution_enabled(Mode.ALL, False) is False


def test_resolve_effective_mode_docker_unavailable_forces_off():
    assert resolve_effective_mode(Mode.ALL, docker_available=False) is Mode.OFF
    assert resolve_effective_mode(Mode.SELECTIVE, docker_available=False) is Mode.OFF
    assert resolve_effective_mode(Mode.OFF, docker_available=False) is Mode.OFF


def test_resolve_effective_mode_docker_available_passthrough():
    assert resolve_effective_mode(Mode.ALL, docker_available=True) is Mode.ALL
    assert resolve_effective_mode(Mode.SELECTIVE, docker_available=True) is Mode.SELECTIVE
    assert resolve_effective_mode(Mode.OFF, docker_available=True) is Mode.OFF


# ── sandbox: config section (config/settings.yaml) ───────────────────────────


def test_load_sandbox_mode_defaults_to_all_when_file_absent(tmp_path, monkeypatch):
    import fleetent.sandbox_enablement as se

    monkeypatch.setattr(se, "SETTINGS_PATH", tmp_path / "missing.yaml")
    assert se.load_sandbox_mode() is Mode.ALL


def test_load_sandbox_mode_defaults_to_all_when_section_absent(tmp_path, monkeypatch):
    import fleetent.sandbox_enablement as se

    p = tmp_path / "settings.yaml"
    p.write_text("log_format: json\n")
    monkeypatch.setattr(se, "SETTINGS_PATH", p)
    assert se.load_sandbox_mode() is Mode.ALL


def test_load_sandbox_mode_reads_configured_value(tmp_path, monkeypatch):
    import fleetent.sandbox_enablement as se

    p = tmp_path / "settings.yaml"
    p.write_text("sandbox:\n  mode: selective\n")
    monkeypatch.setattr(se, "SETTINGS_PATH", p)
    assert se.load_sandbox_mode() is Mode.SELECTIVE


def test_load_sandbox_mode_off(tmp_path, monkeypatch):
    import fleetent.sandbox_enablement as se

    p = tmp_path / "settings.yaml"
    p.write_text("sandbox:\n  mode: off\n")
    monkeypatch.setattr(se, "SETTINGS_PATH", p)
    assert se.load_sandbox_mode() is Mode.OFF


def test_load_sandbox_mode_invalid_falls_back_to_all(tmp_path, monkeypatch):
    import fleetent.sandbox_enablement as se

    p = tmp_path / "settings.yaml"
    p.write_text("sandbox:\n  mode: bogus\n")
    monkeypatch.setattr(se, "SETTINGS_PATH", p)
    assert se.load_sandbox_mode() is Mode.ALL


# ── cached effective-mode resolver (non-server callers: IM gateway / CLI) ────


async def test_get_effective_mode_caches_docker_probe(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    import fleetent.sandbox_client as sc
    import fleetent.sandbox_enablement as se

    monkeypatch.setattr(se, "_effective_mode_cache", None)
    monkeypatch.setattr(se, "SETTINGS_PATH", tmp_path / "missing.yaml")  # default all
    probe = AsyncMock(return_value=True)
    monkeypatch.setattr(sc.SandboxClient, "docker_available", probe)

    first = await se.get_effective_mode()
    second = await se.get_effective_mode()
    assert first is Mode.ALL
    assert second is Mode.ALL
    probe.assert_called_once()  # probe is run once and cached


async def test_get_effective_mode_degrades_when_docker_unavailable(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    import fleetent.sandbox_client as sc
    import fleetent.sandbox_enablement as se

    monkeypatch.setattr(se, "_effective_mode_cache", None)
    monkeypatch.setattr(se, "SETTINGS_PATH", tmp_path / "missing.yaml")
    monkeypatch.setattr(sc.SandboxClient, "docker_available", AsyncMock(return_value=False))

    assert await se.get_effective_mode() is Mode.OFF
