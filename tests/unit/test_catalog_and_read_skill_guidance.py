"""Unit tests: skills catalog + read_skill carry exec-face/SKILLS_DIR guidance.

(skill-read-on-demand). The <available_skills> instruction段 must note that skill
scripts run via run_code and resolve paths under $SKILLS_DIR; `location` renders as a
$SKILLS_DIR-rooted path (not a host-absolute path); read_skill appends the same
guidance; the fixed guidance keeps byte-stable prefix stability across renders.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.skills import registry


@pytest.fixture(autouse=True)
def _isolated_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    user = tmp_path / "skills"
    demo = user / "demo"
    demo.mkdir(parents=True)
    (demo / "SKILL.md").write_text("---\nname: demo\ndescription: handle invoices\n---\nrun me")
    # No package builtins for this test (keep the catalog to the one user skill).
    monkeypatch.setattr(registry, "BUILTIN_SKILLS_DIR", tmp_path / "no_builtins")
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(user))
    registry.scan(str(user))
    return user


def test_catalog_instruction_mentions_run_code_and_skills_dir() -> None:
    prompt = registry.available_skills_prompt()
    assert "run_code" in prompt
    assert "$SKILLS_DIR" in prompt


def test_location_rendered_under_skills_dir_not_host_absolute() -> None:
    prompt = registry.available_skills_prompt()
    # The skill's location is rendered relative to $SKILLS_DIR, not as a host-absolute path.
    assert "<location>$SKILLS_DIR/demo/SKILL.md</location>" in prompt
    # The raw host-absolute SKILL.md path must not leak into the catalog.
    assert str(Path(registry._index["demo"].path)) not in prompt


def test_catalog_byte_stable_across_renders() -> None:
    a = registry.available_skills_prompt()
    b = registry.available_skills_prompt()
    assert a == b  # fixed guidance text → byte-identical prefix


async def test_read_skill_appends_guidance() -> None:
    from fleetent.tools.builtin_tools import read_skill

    body = read_skill("demo")
    assert "run me" in body  # full SKILL.md body
    assert "run_code" in body
    assert "$SKILLS_DIR" in body


async def test_read_skill_unknown_returns_error_text() -> None:
    from fleetent.tools.builtin_tools import read_skill

    result = read_skill("does-not-exist")
    assert result.startswith("error:")
