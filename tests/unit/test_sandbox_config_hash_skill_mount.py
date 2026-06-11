"""Unit tests: skills mount source + mode enter config_hash (sandbox-skill-mount).

Pure digest comparison — changing the skills source or its ro/rw mode must change the
hash (so a reused container rebuilds), while an identical mount keeps it stable.
"""

from __future__ import annotations

from fleetent.integrations.sandbox.backend import SkillMount
from fleetent.integrations.sandbox.config import SandboxResources
from fleetent.integrations.sandbox.hardening import config_hash


def _hash(skill_mount: SkillMount | None) -> str:
    return config_hash(
        image="img",
        resources=SandboxResources(),
        env={"A": "1"},
        workspace_host_path="/ws",
        skill_mount=skill_mount,
    )


def test_same_skill_mount_same_hash() -> None:
    assert _hash(SkillMount("/srv/skills")) == _hash(SkillMount("/srv/skills"))


def test_different_skill_source_different_hash() -> None:
    assert _hash(SkillMount("/srv/skills")) != _hash(SkillMount("/srv/other"))


def test_different_skill_mode_different_hash() -> None:
    ro = SkillMount("/srv/skills", read_only=True)
    rw = SkillMount("/srv/skills", read_only=False)
    assert _hash(ro) != _hash(rw)


def test_none_skill_mount_preserves_legacy_hash() -> None:
    # Backward compatibility: a None skill_mount yields the same digest as the
    # pre-skill-mount signature (no implicit drift for existing containers).
    legacy = config_hash(
        image="img",
        resources=SandboxResources(),
        env={"A": "1"},
        workspace_host_path="/ws",
    )
    assert _hash(None) == legacy
