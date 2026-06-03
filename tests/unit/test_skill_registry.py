import textwrap
from pathlib import Path

import pytest

import fleetent.skill_registry as sr


@pytest.fixture(autouse=True)
def reset_registry():
    sr._index.clear()
    yield
    sr._index.clear()


def test_scan_builds_index(tmp_path):
    skill_dir = tmp_path / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            name: my-skill
            description: Use when user wants to deploy code to production servers.
            ---

            ## Instructions
            Run the deploy script.
        """)
    )
    sr.scan(str(tmp_path / "skills"))
    assert "my-skill" in sr._index
    desc, path = sr._index["my-skill"]
    assert "deploy" in desc.lower()
    assert Path(path).exists()


def test_match_returns_skill_on_keyword(tmp_path):
    skill_dir = tmp_path / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: Use when user wants to deploy code.\n---\nDeploy it."
    )
    sr.scan(str(tmp_path / "skills"))
    assert sr.match("please deploy my application") == "deploy"


def test_match_returns_none_on_no_match(tmp_path):
    skill_dir = tmp_path / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: Use when user wants to deploy code.\n---\nDeploy it."
    )
    sr.scan(str(tmp_path / "skills"))
    assert sr.match("what is the weather today?") is None


def test_load_returns_full_content(tmp_path):
    skill_dir = tmp_path / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    content = "---\nname: my-skill\ndescription: test skill.\n---\n## Do this."
    (skill_dir / "SKILL.md").write_text(content)
    sr.scan(str(tmp_path / "skills"))
    assert sr.load("my-skill") == content


def test_list_skills_returns_name_and_description(tmp_path):
    for name, desc in [("a", "alpha skill"), ("b", "beta skill")]:
        d = tmp_path / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\nInstructions.")
    sr.scan(str(tmp_path / "skills"))
    skills = sr.list_skills()
    names = [s["name"] for s in skills]
    assert "a" in names and "b" in names


# --- SkillIndex (per-agent isolation) ---


def _write_skill(base: Path, name: str, description: str) -> None:
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nBody {name}.")


def test_skillindex_scans_only_its_directory(tmp_path):
    analyst = tmp_path / "analyst"
    _write_skill(analyst, "weekly-report", "Use when user wants the weekly report summary.")
    idx = sr.SkillIndex(str(analyst))
    assert "weekly-report" in [s["name"] for s in idx.list_skills()]
    assert idx.match("please generate the weekly report") == "weekly-report"
    assert "Body weekly-report." in idx.load("weekly-report")


def test_skillindex_does_not_pollute_global_index(tmp_path):
    analyst = tmp_path / "analyst"
    _write_skill(analyst, "weekly-report", "Use when user wants the weekly report.")
    sr.SkillIndex(str(analyst))
    # global module index untouched by the instance scan
    assert "weekly-report" not in sr._index


def test_skillindex_isolated_from_each_other(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write_skill(a, "alpha", "Use when provisioning compute clusters.")
    _write_skill(b, "beta", "Use when archiving cold storage backups.")
    idx_a = sr.SkillIndex(str(a))
    idx_b = sr.SkillIndex(str(b))
    assert idx_a.match("help me provisioning a cluster") == "alpha"
    assert idx_b.match("help me provisioning a cluster") is None
    assert idx_b.match("archiving old backups") == "beta"
