from __future__ import annotations

import os
from pathlib import Path

import pytest


def _write_skill(pool_dir: Path, skill_name: str) -> Path:
    skill_dir = pool_dir / skill_name
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: Review incidents\n---\nbody\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
    return skill_dir


def test_bundle_cache_rejects_path_escape(tmp_path: Path) -> None:
    from fleetent.platform.skill_management import bundle_cache

    skill_dir = _write_skill(tmp_path / "pool", "incident-review")

    with pytest.raises(ValueError, match="unsafe bundle path"):
        bundle_cache._bundle_member_name(skill_dir, tmp_path / "escape.txt")  # noqa: SLF001


def test_bundle_cache_rejects_symlink_and_hardlink_entries(tmp_path: Path) -> None:
    from fleetent.platform.skill_management import bundle_cache

    pool_dir = tmp_path / "pool"
    cache_dir = tmp_path / "cache"
    skill_dir = _write_skill(pool_dir, "incident-review")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    os.symlink(outside, skill_dir / "linked.txt")

    with pytest.raises(ValueError, match="symlink"):
        bundle_cache.ensure_bundle_cached(
            pool_dir=pool_dir,
            cache_dir=cache_dir,
            skill_name="incident-review",
            base_version="abc123",
        )

    (skill_dir / "linked.txt").unlink()
    os.link(outside, skill_dir / "hardlinked.txt")

    with pytest.raises(ValueError, match="hardlink"):
        bundle_cache.ensure_bundle_cached(
            pool_dir=pool_dir,
            cache_dir=cache_dir,
            skill_name="incident-review",
            base_version="abc123",
        )
