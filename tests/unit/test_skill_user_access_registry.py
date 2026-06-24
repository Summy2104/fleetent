"""registry per-user visibility + session filtered view (skill-user-access)."""

from __future__ import annotations

import pytest

import fleetent.skills.registry as sr

ACCESS = {"secret": ["U1", "U2"]}  # 'secret' restricted; 'public' absent => public


# --- skill_visible_to_user (task 2.1/2.2) ---


def test_public_skill_visible_to_anyone_any_chat() -> None:
    assert sr.skill_visible_to_user("public", user_id="U9", chat_type="channel", access_map=ACCESS)
    assert sr.skill_visible_to_user("public", user_id="U9", chat_type="dm", access_map=ACCESS)


def test_restricted_visible_to_listed_user_in_dm() -> None:
    assert sr.skill_visible_to_user("secret", user_id="U1", chat_type="dm", access_map=ACCESS)


def test_restricted_hidden_from_unlisted_user_in_dm() -> None:
    assert not sr.skill_visible_to_user("secret", user_id="U9", chat_type="dm", access_map=ACCESS)


def test_restricted_hidden_in_channel_even_for_listed_user() -> None:
    assert not sr.skill_visible_to_user(
        "secret", user_id="U1", chat_type="channel", access_map=ACCESS
    )


def test_empty_access_map_everything_visible() -> None:
    assert sr.skill_visible_to_user("secret", user_id="U9", chat_type="channel", access_map={})


# --- build_session_skill_view (task 5.1/5.2) ---


@pytest.fixture
def skills_root(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_no_builtin")
    root = tmp_path / "skills"
    for n in ("public", "secret", "other"):
        d = root / n
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {n}\ndescription: {n}.\n---\nbody-{n}\n")
        (d / "scripts").mkdir()
        (d / "scripts" / "run.py").write_text(f"# {n} script\n")
    sr._index.clear()
    yield root
    sr._index.clear()


def test_view_contains_only_allowed_skills(skills_root):
    view = sr.build_session_skill_view("sess-1", ["public", "secret"], skills_dir=str(skills_root))
    from pathlib import Path

    v = Path(view)
    pub = "---\nname: public\ndescription: public.\n---\nbody-public\n"
    assert (v / "public" / "SKILL.md").read_text() == pub
    assert (v / "secret" / "SKILL.md").is_file()
    assert (v / "secret" / "scripts" / "run.py").is_file()  # whole tree, incl scripts
    assert not (v / "other").exists()  # filtered out


def test_view_rebuild_is_idempotent(skills_root):
    sr.build_session_skill_view("sess-1", ["public", "secret"], skills_dir=str(skills_root))
    view = sr.build_session_skill_view("sess-1", ["public"], skills_dir=str(skills_root))
    from pathlib import Path

    v = Path(view)
    assert (v / "public").exists()
    assert not (v / "secret").exists()  # rebuild reflects new allowed set


def test_scan_ignores_view_dir(skills_root):
    sr.build_session_skill_view("sess-1", ["public", "secret"], skills_dir=str(skills_root))
    sr.scan(str(skills_root))
    # the .views/<key>/ hardlinks must NOT be re-indexed as extra skills
    assert set(sr._index) == {"public", "secret", "other"}
