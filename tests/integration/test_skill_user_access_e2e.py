"""End-to-end per-skill user access across all three layers (skill-user-access).

catalog hide + read_skill refuse + per-session view exclusion, over real skill files.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import fleetent.skills.registry as sr
from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext

ACCESS = {"secret": ["U1"]}  # secret restricted to U1; public is open


@pytest.fixture
def skills(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_nb")
    root = tmp_path / "skills"
    for n in ("public", "secret"):
        d = root / n
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {n}\ndescription: {n} skill.\n---\nbody-{n}\n")
        (d / "scripts").mkdir()
        (d / "scripts" / "run.py").write_text(f"# {n}\n")
    sr._index.clear()
    sr.scan(str(root))
    yield root
    sr._index.clear()


def _ctx(user_id, chat_type):
    return ToolContext(
        scope_key=f"{chat_type}:{user_id}",
        principal=SimpleNamespace(user_id=user_id),
        session_context=SimpleNamespace(chat_type=chat_type),
        skill_user_access=ACCESS,
    )


def test_authorized_dm_user_full_access(skills):
    # catalog: secret visible
    cat = sr.available_skills_prompt(user_id="U1", chat_type="dm", skill_user_access=ACCESS)
    assert "secret" in cat and "public" in cat
    # read_skill: loads
    assert "body-secret" in builtin_tools.read_skill("secret", tool_context=_ctx("U1", "dm"))
    # view: secret present
    v = Path(builtin_tools._skill_view_source(_ctx("U1", "dm")))
    assert (v / "secret" / "scripts" / "run.py").exists()
    assert (v / "public").exists()


def test_unauthorized_dm_user_blocked_all_layers(skills):
    cat = sr.available_skills_prompt(user_id="U9", chat_type="dm", skill_user_access=ACCESS)
    assert "secret" not in cat and "public" in cat
    out = builtin_tools.read_skill("secret", tool_context=_ctx("U9", "dm"))
    assert out == "error: no skill named 'secret'"
    v = Path(builtin_tools._skill_view_source(_ctx("U9", "dm")))
    assert not (v / "secret").exists() and (v / "public").exists()


def test_channel_blocks_restricted_for_all(skills):
    cat = sr.available_skills_prompt(user_id="U1", chat_type="channel", skill_user_access=ACCESS)
    assert "secret" not in cat  # restricted = DM-only, hidden in channel even for U1
    out = builtin_tools.read_skill("secret", tool_context=_ctx("U1", "channel"))
    assert out == "error: no skill named 'secret'"
    v = Path(builtin_tools._skill_view_source(_ctx("U1", "channel")))
    assert not (v / "secret").exists() and (v / "public").exists()
