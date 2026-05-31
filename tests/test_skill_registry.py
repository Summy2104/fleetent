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
def reset_registry(tmp_path, monkeypatch):
    # Isolate the package builtin dir to an absent path by default so tests that
    # don't exercise builtins keep pre-change behavior; builtin tests opt in by
    # re-monkeypatching BUILTIN_SKILLS_DIR.
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_no_builtin")
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


# --- nested recursive scan (SK7) ---


def test_scan_discovers_deeply_nested_skill(tmp_path):
    nested = tmp_path / "skills" / "crm" / "contracts"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text(
        "---\nname: contracts\ndescription: Use when user wants to review contracts.\n---\nbody"
    )
    sr.scan(str(tmp_path / "skills"))
    assert "contracts" in sr._index
    assert Path(sr._index["contracts"].path).exists()


def test_scan_includes_mixed_level_skills(tmp_path):
    top = tmp_path / "skills" / "deploy"
    top.mkdir(parents=True)
    (top / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: Use when user wants to deploy code.\n---\nbody"
    )
    deep = tmp_path / "skills" / "team-a" / "billing"
    deep.mkdir(parents=True)
    (deep / "SKILL.md").write_text(
        "---\nname: billing\ndescription: Use when user wants to handle billing.\n---\nbody"
    )
    sr.scan(str(tmp_path / "skills"))
    assert "deploy" in sr._index
    assert "billing" in sr._index


def test_scan_nested_name_falls_back_to_parent_dir(tmp_path):
    nested = tmp_path / "skills" / "crm" / "contracts"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text("---\ndescription: no explicit name here.\n---\nbody")
    sr.scan(str(tmp_path / "skills"))
    assert "contracts" in sr._index


def test_scan_missing_dir_returns_empty(tmp_path):
    sr.scan(str(tmp_path / "does-not-exist"))
    assert sr._index == {}


# --- name conflict warning + deterministic selection (SK8) ---


def _write_named_skill(tmp_path, dirname, name, description="conflict skill."):
    d = tmp_path / "skills" / dirname
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nbody")


def test_scan_same_name_conflict_warns_with_both_paths(tmp_path):
    _write_named_skill(tmp_path, "alpha", "dup")
    _write_named_skill(tmp_path, "beta", "dup")
    with structlog.testing.capture_logs() as logs:
        sr.scan(str(tmp_path / "skills"))
    warnings = [e for e in logs if e["log_level"] == "warning"]
    conflict = [e for e in warnings if e.get("name") == "dup"]
    assert len(conflict) == 1
    entry = conflict[0]
    paths = {str(entry.get("kept_path")), str(entry.get("dropped_path"))}
    assert any(p.endswith("/alpha/SKILL.md") for p in paths)
    assert any(p.endswith("/beta/SKILL.md") for p in paths)


def test_scan_conflict_keeps_path_sorted_first(tmp_path):
    _write_named_skill(tmp_path, "alpha", "dup")
    _write_named_skill(tmp_path, "beta", "dup")
    with structlog.testing.capture_logs():
        sr.scan(str(tmp_path / "skills"))
    assert "dup" in sr._index
    assert sr._index["dup"].path.endswith("/alpha/SKILL.md")


def test_scan_conflict_winner_independent_of_arrival_order(tmp_path, monkeypatch):
    _write_named_skill(tmp_path, "alpha", "dup")
    _write_named_skill(tmp_path, "beta", "dup")
    base = tmp_path / "skills"
    alpha = base / "alpha" / "SKILL.md"
    beta = base / "beta" / "SKILL.md"

    real_rglob = Path.rglob

    def reversed_rglob(self, pattern):
        return list(reversed(list(real_rglob(self, pattern))))

    with structlog.testing.capture_logs():
        monkeypatch.setattr(Path, "rglob", reversed_rglob)
        sr.scan(str(base))
        winner_reversed = sr._index["dup"].path

        monkeypatch.setattr(Path, "rglob", real_rglob)
        sr.scan(str(base))
        winner_forward = sr._index["dup"].path

    assert winner_reversed == winner_forward
    assert winner_forward == str(alpha)
    assert winner_forward != str(beta)


def test_scan_triple_conflict_warns_per_loser(tmp_path):
    _write_named_skill(tmp_path, "aaa", "trip")
    _write_named_skill(tmp_path, "bbb", "trip")
    _write_named_skill(tmp_path, "ccc", "trip")
    with structlog.testing.capture_logs() as logs:
        sr.scan(str(tmp_path / "skills"))
    conflict = [e for e in logs if e["log_level"] == "warning" and e.get("name") == "trip"]
    assert len(conflict) == 2
    assert sr._index["trip"].path.endswith("/aaa/SKILL.md")


def test_scan_distinct_names_no_conflict_warning(tmp_path):
    _write_named_skill(tmp_path, "alpha", "one")
    _write_named_skill(tmp_path, "beta", "two")
    with structlog.testing.capture_logs() as logs:
        sr.scan(str(tmp_path / "skills"))
    assert "one" in sr._index
    assert "two" in sr._index
    assert not [e for e in logs if e["log_level"] == "warning" and "name" in e]


# --- builtin skills + disable switch (builtin-skills) ---


def _write_builtin_skill(tmp_path, name, description="builtin skill."):
    d = tmp_path / "builtin" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nbody")


def test_scan_marks_builtin_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "builtin")
    _write_builtin_skill(tmp_path, "intro", "Use when user wants an intro guide.")
    sr.scan(str(tmp_path / "skills"))
    assert "intro" in sr._index
    assert sr._index["intro"].builtin is True


def test_scan_marks_user_skill_not_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "builtin")
    _write_skill(tmp_path, "mine", "---\nname: mine\ndescription: user skill.\n---\nbody")
    sr.scan(str(tmp_path / "skills"))
    assert "mine" in sr._index
    assert sr._index["mine"].builtin is False


def test_scan_builtin_and_user_both_indexed(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "builtin")
    _write_builtin_skill(tmp_path, "bi", "builtin one.")
    _write_skill(tmp_path, "us", "---\nname: us\ndescription: user one.\n---\nbody")
    sr.scan(str(tmp_path / "skills"))
    assert sr._index["bi"].builtin is True
    assert sr._index["us"].builtin is False


def test_scan_missing_builtin_dir_does_not_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "absent-builtin")
    _write_skill(tmp_path, "us", "---\nname: us\ndescription: user one.\n---\nbody")
    sr.scan(str(tmp_path / "skills"))
    assert "us" in sr._index


def test_shipped_builtin_dir_exists():
    # Regression: the package ships at least one builtin SKILL.md so a fresh
    # deployment is non-empty. Use the real package path, not the per-test
    # monkeypatched attribute.
    real_builtin = Path(sr.__file__).parent / "builtin_skills"
    assert real_builtin.is_dir()
    assert list(real_builtin.rglob("SKILL.md"))


# --- regression: scan introduces no source-priority override (D2 / SK8) ---


def test_scan_no_source_priority_override_logic(tmp_path, monkeypatch):
    # builtin-skills must NOT pick a same-name winner by source; conflict
    # resolution is SK8's full-path-string sort, independent of source. The
    # winner is whichever SKILL.md path sorts first, not "builtin wins".
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "builtin")
    builtin_md = tmp_path / "builtin" / "dir-z" / "SKILL.md"
    builtin_md.parent.mkdir(parents=True)
    builtin_md.write_text("---\nname: dup\ndescription: builtin dup.\n---\nbody")
    user_md = tmp_path / "skills" / "dir-a" / "SKILL.md"
    user_md.parent.mkdir(parents=True)
    user_md.write_text("---\nname: dup\ndescription: user dup.\n---\nbody")
    with structlog.testing.capture_logs():
        sr.scan(str(tmp_path / "skills"))
    expected_winner = sorted((str(builtin_md), str(user_md)))[0]
    assert sr._index["dup"].path == expected_winner


# --- disabled_skills injection (task 4) ---


def test_settings_has_disabled_skills_default_empty(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    from fleetent.config import Settings

    assert Settings().disabled_skills == []


def test_match_disabled_skills_param_overrides(tmp_path):
    _write_skill(tmp_path, "deploy", "---\nname: deploy\ndescription: deploy code now.\n---\nb")
    sr.scan(str(tmp_path / "skills"))
    with structlog.testing.capture_logs():
        assert sr.match("please deploy code", disabled_skills=["deploy"]) is None
        assert sr.match("please deploy code", disabled_skills=[]) == "deploy"


# --- enabled_by_default wiring to match (task 5) ---


def test_match_skips_disabled_by_default(tmp_path):
    _write_skill(
        tmp_path,
        "off",
        "---\nname: off\ndescription: deploy code now.\nenabled_by_default: false\n---\nb",
    )
    sr.scan(str(tmp_path / "skills"))
    with structlog.testing.capture_logs():
        assert sr.match("please deploy code now") is None


def test_match_default_enabled_when_unspecified(tmp_path):
    _write_skill(tmp_path, "enabled", "---\nname: enabled\ndescription: deploy code now.\n---\nb")
    sr.scan(str(tmp_path / "skills"))
    assert sr.match("please deploy code now") == "enabled"


# --- config force-disable + observability + load unaffected (task 6) ---


def test_match_config_disabled_logs_reason(tmp_path):
    _write_skill(tmp_path, "deploy", "---\nname: deploy\ndescription: deploy code now.\n---\nb")
    sr.scan(str(tmp_path / "skills"))
    with structlog.testing.capture_logs() as logs:
        result = sr.match("please deploy code now", disabled_skills=["deploy"])
    assert result is None
    disabled_logs = [e for e in logs if e.get("name") == "deploy"]
    assert disabled_logs
    assert any(e.get("reason") == "disabled_skills_config" for e in disabled_logs)


def test_match_default_disabled_logs_reason(tmp_path):
    _write_skill(
        tmp_path,
        "off",
        "---\nname: off\ndescription: deploy code now.\nenabled_by_default: false\n---\nb",
    )
    sr.scan(str(tmp_path / "skills"))
    with structlog.testing.capture_logs() as logs:
        sr.match("please deploy code now")
    disabled_logs = [e for e in logs if e.get("name") == "off"]
    assert any(e.get("reason") == "enabled_by_default_false" for e in disabled_logs)


def test_load_unaffected_by_default_disable(tmp_path):
    content = "---\nname: off\ndescription: d.\nenabled_by_default: false\n---\nbody"
    d = tmp_path / "skills" / "off"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(content)
    sr.scan(str(tmp_path / "skills"))
    assert sr.load("off") == content


def test_load_unaffected_by_config_disable(tmp_path):
    content = "---\nname: deploy\ndescription: deploy code.\n---\nbody"
    d = tmp_path / "skills" / "deploy"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(content)
    sr.scan(str(tmp_path / "skills"))
    # load takes no disable list; disable judgment must not gate load at all.
    assert sr.load("deploy") == content


# --- regression: default config leaves all skills matchable (task 7.3) ---


def test_default_config_all_skills_match(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "absent")
    _write_skill(tmp_path, "deploy", "---\nname: deploy\ndescription: deploy code now.\n---\nb")
    sr.scan(str(tmp_path / "skills"))
    # No disabled_skills passed; lazy Settings read yields empty list default.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    assert sr.match("please deploy code now") == "deploy"


# env var rename (SK9)
def test_scan_uses_fleetent_skills_dir_env(tmp_path, monkeypatch):
    _write_skill(
        tmp_path,
        "alpha",
        """\
        ---
        name: alpha
        description: alpha skill
        ---
        body
        """,
    )
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.delenv("MINI_AGENT_SKILLS_DIR", raising=False)
    sr.scan()
    assert "alpha" in sr._index


def test_scan_ignores_old_env_var_name(tmp_path, monkeypatch):
    # skill lives in a NON-"skills" dir; only the old env var points at it.
    skilldir = tmp_path / "oldspot" / "beta"
    skilldir.mkdir(parents=True)
    (skilldir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: beta
        description: beta skill
        ---
        body
        """)
    )
    monkeypatch.delenv("FLEETENT_SKILLS_DIR", raising=False)
    monkeypatch.setenv("MINI_AGENT_SKILLS_DIR", str(tmp_path / "oldspot"))
    monkeypatch.chdir(tmp_path)  # old name ignored -> default "skills" (absent here)
    sr.scan()
    assert "beta" not in sr._index
