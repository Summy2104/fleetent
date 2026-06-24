"""available_skills_prompt per-user filtering (skill-user-access)."""

from __future__ import annotations

import pytest

import fleetent.skills.registry as sr


@pytest.fixture(autouse=True)
def reset_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_no_builtin")
    sr._index.clear()
    yield
    sr._index.clear()


def _mk(tmp_path, name):
    d = tmp_path / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name} skill.\n---\nbody\n")


ACCESS = {"secret": ["U1"]}


def _catalog(tmp_path, **kw):
    return sr.available_skills_prompt(skill_user_access=ACCESS, **kw)


def test_restricted_hidden_from_unauthorized_dm(tmp_path):
    _mk(tmp_path, "public")
    _mk(tmp_path, "secret")
    sr.scan(str(tmp_path / "skills"))
    out = _catalog(tmp_path, user_id="U9", chat_type="dm")
    assert "public" in out and "secret" not in out


def test_restricted_shown_to_authorized_dm(tmp_path):
    _mk(tmp_path, "public")
    _mk(tmp_path, "secret")
    sr.scan(str(tmp_path / "skills"))
    out = _catalog(tmp_path, user_id="U1", chat_type="dm")
    assert "secret" in out


def test_restricted_hidden_in_channel(tmp_path):
    _mk(tmp_path, "secret")
    sr.scan(str(tmp_path / "skills"))
    out = _catalog(tmp_path, user_id="U1", chat_type="channel")
    assert "secret" not in out


def test_no_access_map_unchanged(tmp_path):
    _mk(tmp_path, "secret")
    sr.scan(str(tmp_path / "skills"))
    # no skill_user_access => everything visible (backward compat)
    out = sr.available_skills_prompt(user_id="U9", chat_type="channel")
    assert "secret" in out
