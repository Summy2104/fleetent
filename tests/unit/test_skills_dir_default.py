"""The global skills dir defaults to <home>/skills (under FLEETENT_HOME)."""

from fleetent.skills.registry import _resolve_skills_dir


def test_default_resolves_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_SKILLS_DIR", raising=False)
    assert _resolve_skills_dir(None) == str(tmp_path / "skills")


def test_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", "/custom/skills")
    assert _resolve_skills_dir(None) == "/custom/skills"


def test_explicit_arg_passthrough(monkeypatch):
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", "/env/skills")
    assert _resolve_skills_dir("/explicit") == "/explicit"
