"""Unit tests: single effective skills root + builtin materialization (D3).

The effective root is the USER skills root (not the package builtin dir); package
builtin skills are materialized (copied) into it idempotently, never overwriting a
user-authored same-name skill. Pure filesystem work on tmp dirs — no docker, no DB.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.skills import registry


@pytest.fixture(autouse=True)
def _builtin_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point BUILTIN_SKILLS_DIR at a tmp package-root with one builtin skill+resource."""
    builtin = tmp_path / "builtin_skills"
    skill = builtin / "starter"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: starter\ndescription: d\n---\nbody")
    (skill / "data.txt").write_text("payload")
    monkeypatch.setattr(registry, "BUILTIN_SKILLS_DIR", builtin)
    return builtin


def test_effective_root_is_user_root(tmp_path: Path) -> None:
    user = tmp_path / "user_skills"
    root = registry.effective_skill_root(str(user))
    assert Path(root) == user
    assert Path(root).is_dir()  # created if missing


def test_materialize_copies_builtin_resources(tmp_path: Path) -> None:
    user = tmp_path / "user_skills"
    registry.materialize_builtin_skills(str(user))
    assert (user / "starter" / "SKILL.md").exists()
    assert (user / "starter" / "data.txt").read_text() == "payload"


def test_materialize_is_idempotent(tmp_path: Path) -> None:
    user = tmp_path / "user_skills"
    registry.materialize_builtin_skills(str(user))
    registry.materialize_builtin_skills(str(user))  # second run must not raise
    assert (user / "starter" / "data.txt").read_text() == "payload"


def test_materialize_does_not_overwrite_user_skill(tmp_path: Path) -> None:
    user = tmp_path / "user_skills"
    user_skill = user / "starter"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text("---\nname: starter\ndescription: mine\n---\ncustom")
    registry.materialize_builtin_skills(str(user))
    # User content wins (user-overrides-builtin); the builtin resource is NOT injected.
    assert (
        user_skill / "SKILL.md"
    ).read_text() == "---\nname: starter\ndescription: mine\n---\ncustom"
    assert not (user_skill / "data.txt").exists()
