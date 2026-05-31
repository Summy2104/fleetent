import textwrap
from pathlib import Path

import pytest
import structlog

import fleetent.skill_registry as sr


def _write_skill(tmp_path, name, body):
    d = tmp_path / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(textwrap.dedent(body))


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
    entry = sr._index["my-skill"]
    assert "deploy" in entry.description.lower()
    assert Path(entry.path).exists()


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


# --- YAML parsing (task 2) ---


def test_parse_frontmatter_inline_list():
    fm = sr._parse_frontmatter(
        textwrap.dedent("""\
            ---
            name: crm
            description: CRM skill.
            tags: [crm, sales]
            ---
            body
        """)
    )
    assert fm is not None
    assert fm["tags"] == ["crm", "sales"]


def test_parse_frontmatter_multiline_list():
    fm = sr._parse_frontmatter(
        textwrap.dedent("""\
            ---
            name: crm
            description: CRM skill.
            tags:
              - crm
              - sales
            ---
            body
        """)
    )
    assert fm is not None
    assert fm["tags"] == ["crm", "sales"]


def test_parse_frontmatter_bool_and_number():
    fm = sr._parse_frontmatter(
        textwrap.dedent("""\
            ---
            name: x
            description: d
            enabled_by_default: false
            version: 2
            ---
            body
        """)
    )
    assert fm is not None
    assert fm["enabled_by_default"] is False
    assert fm["version"] == 2


# --- parse failure (task 3) ---


def test_parse_frontmatter_no_leading_delimiter_returns_none():
    assert sr._parse_frontmatter("name: x\ndescription: d\n") is None


def test_parse_frontmatter_no_closing_delimiter_returns_none():
    assert sr._parse_frontmatter("---\nname: x\ndescription: d\n") is None


def test_parse_frontmatter_invalid_yaml_returns_none():
    assert sr._parse_frontmatter("---\nname: [unclosed\n---\nbody") is None


def test_parse_frontmatter_non_mapping_returns_none():
    assert sr._parse_frontmatter("---\n- just\n- a\n- list\n---\nbody") is None


def test_scan_skips_broken_yaml_and_warns(tmp_path):
    _write_skill(tmp_path, "broken", "---\nname: [unclosed\n---\nbody")
    with structlog.testing.capture_logs() as logs:
        sr.scan(str(tmp_path / "skills"))
    assert "broken" not in sr._index
    warnings = [e for e in logs if e["log_level"] == "warning"]
    assert any("broken" in str(e.get("path", "")) for e in warnings)


def test_scan_skips_missing_boundary_and_warns(tmp_path):
    _write_skill(tmp_path, "noboundary", "name: x\ndescription: d\n")
    with structlog.testing.capture_logs() as logs:
        sr.scan(str(tmp_path / "skills"))
    assert "noboundary" not in sr._index
    assert any(e["log_level"] == "warning" for e in logs)


def test_scan_skips_non_mapping_and_warns(tmp_path):
    _write_skill(tmp_path, "listtop", "---\n- a\n- b\n---\nbody")
    with structlog.testing.capture_logs() as logs:
        sr.scan(str(tmp_path / "skills"))
    assert "listtop" not in sr._index
    assert any(e["log_level"] == "warning" for e in logs)


def test_scan_valid_skill_does_not_warn(tmp_path):
    _write_skill(tmp_path, "ok", "---\nname: ok\ndescription: valid skill.\n---\nbody")
    with structlog.testing.capture_logs() as logs:
        sr.scan(str(tmp_path / "skills"))
    assert "ok" in sr._index
    assert not [e for e in logs if e["log_level"] == "warning"]


# --- extended fields (task 4) ---


def test_scan_carries_extended_fields(tmp_path):
    _write_skill(
        tmp_path,
        "full",
        """\
            ---
            name: full
            description: full skill.
            tags: [crm, sales]
            platforms: [slack, telegram]
            version: 1.2
            enabled_by_default: false
            ---
            body
        """,
    )
    sr.scan(str(tmp_path / "skills"))
    e = sr._index["full"]
    assert e.tags == ["crm", "sales"]
    assert e.platforms == ["slack", "telegram"]
    assert e.version == "1.2"
    assert e.enabled_by_default is False


def test_scan_extended_fields_defaults(tmp_path):
    _write_skill(tmp_path, "min", "---\nname: min\ndescription: deploy code skill.\n---\nbody")
    sr.scan(str(tmp_path / "skills"))
    e = sr._index["min"]
    assert e.tags == []
    assert e.platforms == []
    assert e.version is None
    assert e.enabled_by_default is True
    assert sr.match("please deploy code now") == "min"
    assert sr.load("min").startswith("---")


def test_scan_scalar_tag_normalized_to_list(tmp_path):
    _write_skill(tmp_path, "s", "---\nname: s\ndescription: d.\ntags: crm\n---\nbody")
    sr.scan(str(tmp_path / "skills"))
    assert sr._index["s"].tags == ["crm"]
