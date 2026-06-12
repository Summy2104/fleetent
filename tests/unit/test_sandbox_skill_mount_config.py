"""Unit tests: sandbox.skill_mount config namespace (sandbox-skill-mount).

Per-agent `SandboxSettings.skill_mount` (enabled default true, read_only default true,
optional source) under `extra="forbid"`: legal fields parse, unknown fields are
rejected. Platform `sandbox.skill_mount` parses the same fields via load_skill_mount_config.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fleetent.agent_config import SandboxSettings
from fleetent.integrations.sandbox.config import SkillMountConfig, load_skill_mount_config


def test_skill_mount_defaults() -> None:
    s = SandboxSettings()
    assert s.skill_mount.enabled is True
    assert s.skill_mount.read_only is True
    assert s.skill_mount.source is None


def test_skill_mount_explicit_fields() -> None:
    s = SandboxSettings.model_validate(
        {"skill_mount": {"enabled": False, "read_only": False, "source": "/srv/skills"}}
    )
    assert s.skill_mount.enabled is False
    assert s.skill_mount.read_only is False
    assert s.skill_mount.source == "/srv/skills"


def test_skill_mount_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        SandboxSettings.model_validate({"skill_mount": {"bogus": 1}})


def test_platform_skill_mount_loaded(tmp_path: Path) -> None:
    cfg_file = tmp_path / "platform.yaml"
    cfg_file.write_text(
        "sandbox:\n"
        "  skill_mount:\n"
        "    enabled: false\n"
        "    read_only: false\n"
        "    source: /opt/skills\n"
    )
    loaded = load_skill_mount_config(cfg_file)
    assert loaded == SkillMountConfig(enabled=False, read_only=False, source="/opt/skills")


def test_platform_skill_mount_defaults_when_absent(tmp_path: Path) -> None:
    cfg_file = tmp_path / "platform.yaml"
    cfg_file.write_text("sandbox:\n  scope: session\n")
    assert load_skill_mount_config(cfg_file) == SkillMountConfig()
