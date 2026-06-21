"""skill_manage write -> reload -> read_skill roundtrip over real files (agent-skill-tools).

Real filesystem CRUD through the registry + tools, so it lives in integration.
"""

from __future__ import annotations

import pytest

import fleetent.skills.registry as sr
from fleetent.tools import builtin_tools

_CONTENT = "---\nname: roundtrip\ndescription: a roundtrip skill.\n---\n## Steps\nDo it.\n"


@pytest.fixture
def skills_root(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_no_builtin")
    root = tmp_path / "skills"
    root.mkdir()
    sr._index.clear()
    sr.scan(str(root))
    yield root
    sr._index.clear()


def test_skill_manage_create_edit_delete_roundtrip(skills_root):
    # create -> index + readable
    out = builtin_tools.skill_manage(action="create", name="roundtrip", content=_CONTENT)
    assert "ok" in out.lower()
    assert "roundtrip" in sr._index
    assert (skills_root / "roundtrip" / "SKILL.md").is_file()

    body = builtin_tools.read_skill("roundtrip")
    assert "## Steps" in body
    assert "agent_tool" in body  # provenance stamped on create

    # write_file + read it back via read_skill file_path
    builtin_tools.skill_manage(
        action="write_file",
        name="roundtrip",
        file_path="references/notes.md",
        file_content="NOTE BODY",
    )
    assert builtin_tools.read_skill("roundtrip", file_path="references/notes.md") == "NOTE BODY"

    # edit -> new body visible
    builtin_tools.skill_manage(
        action="edit",
        name="roundtrip",
        content="---\nname: roundtrip\ndescription: edited.\n---\n## New\n",
    )
    assert "## New" in builtin_tools.read_skill("roundtrip")

    # delete -> gone
    builtin_tools.skill_manage(action="delete", name="roundtrip")
    assert "roundtrip" not in sr._index
    assert not (skills_root / "roundtrip").exists()
