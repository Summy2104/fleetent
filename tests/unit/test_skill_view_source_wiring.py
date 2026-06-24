"""run_code/file-tool acquire computes a per-session skill view source (skill-user-access)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fleetent.skills.registry as sr
from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


def _seed_skills(tmp_path):
    for n in ("public", "secret"):
        d = tmp_path / "skills" / n
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {n}\ndescription: {n}.\n---\nbody\n")
    sr.scan(str(tmp_path / "skills"))


def _ctx(user_id, chat_type, scope_key="sk1"):
    return ToolContext(
        scope_key=scope_key,
        principal=SimpleNamespace(user_id=user_id),
        session_context=SimpleNamespace(chat_type=chat_type),
        skill_user_access={"secret": ["U1"]},
    )


def test_view_source_excludes_restricted_for_unauthorized(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_nb")
    _seed_skills(tmp_path)
    src = builtin_tools._skill_view_source(_ctx("U9", "dm"))
    assert src is not None
    v = Path(src)
    assert (v / "public").exists() and not (v / "secret").exists()


def test_view_source_includes_restricted_for_authorized_dm(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_nb")
    _seed_skills(tmp_path)
    v = Path(builtin_tools._skill_view_source(_ctx("U1", "dm")))
    assert (v / "public").exists() and (v / "secret").exists()


def test_view_source_none_when_no_access_map(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_nb")
    _seed_skills(tmp_path)
    ctx = ToolContext(scope_key="sk1", principal=SimpleNamespace(user_id="U1"),
                      session_context=SimpleNamespace(chat_type="dm"))  # empty access map
    assert builtin_tools._skill_view_source(ctx) is None
