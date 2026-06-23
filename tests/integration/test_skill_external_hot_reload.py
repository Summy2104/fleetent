"""External-file skill hot-reload end-to-end over real files (skill-external-hot-reload).

Simulates a running agent: scan once, then external add/edit/delete picked up by
refresh_if_changed and reflected in the injected catalog — no restart. Real filesystem,
so it lives in integration.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

import fleetent.skills.registry as sr


@pytest.fixture
def skills_root(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_no_builtin")
    root = tmp_path / "skills"
    root.mkdir()
    sr._index.clear()
    sr._manifest.clear()
    yield root
    sr._index.clear()
    sr._manifest.clear()


def _write(root, name, desc):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        textwrap.dedent(f"""\
            ---
            name: {name}
            description: {desc}
            ---
            body
        """)
    )


def test_external_add_edit_delete_reflected_in_catalog(skills_root):
    _write(skills_root, "alpha", "Alpha skill.")
    sr.scan(str(skills_root))
    assert "alpha" in sr.available_skills_prompt()

    # external add -> picked up, catalog includes it
    _write(skills_root, "beta", "Beta skill.")
    assert sr.refresh_if_changed(str(skills_root)) is True
    assert "beta" in sr.available_skills_prompt()

    # external edit -> new description reflected
    _write(skills_root, "alpha", "Alpha skill EDITED externally.")
    assert sr.refresh_if_changed(str(skills_root)) is True
    assert "EDITED externally" in sr.available_skills_prompt()

    # external delete -> drops from catalog
    shutil.rmtree(skills_root / "beta")
    assert sr.refresh_if_changed(str(skills_root)) is True
    assert "beta" not in sr.available_skills_prompt()

    # no change -> no reload
    assert sr.refresh_if_changed(str(skills_root)) is False


def test_disabled_flag_skips_refresh(skills_root):
    """With skill_hot_reload off, the runtime helper must not refresh."""
    from fleetent.runtime import loop

    _write(skills_root, "alpha", "Alpha skill.")
    sr.scan(str(skills_root))
    _write(skills_root, "beta", "Beta skill.")  # external add

    loop._maybe_refresh_skills(False)  # disabled -> no refresh
    assert "beta" not in sr.available_skills_prompt()

    loop._maybe_refresh_skills(True)  # enabled -> picks it up
    assert "beta" in sr.available_skills_prompt()
