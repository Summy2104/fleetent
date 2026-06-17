"""Unit tests: sandbox.skill_mount config namespace (sandbox-skill-mount).

Per-agent `SandboxSettings.skill_mount` (enabled default true, read_only default true,
optional source) under `extra="forbid"`: legal fields parse, unknown fields are
rejected. skill_mount is per-agent only now (per-agent-sandbox-resources removed the
machine-shared platform.yaml `sandbox.skill_mount` loader).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fleetent.agent_config import SandboxSettings


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
