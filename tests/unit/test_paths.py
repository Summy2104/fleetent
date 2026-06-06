"""Resolution-precedence tests for the central runtime path resolver."""

from pathlib import Path

import pytest

from fleetent import paths

REPO_PYPROJECT = '[project]\nname = "fleetent"\n'


@pytest.fixture
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point Path.home() at a temp dir and clear FLEETENT_HOME."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    return home


def _make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(REPO_PYPROJECT)
    return root


def test_explicit_fleetent_home_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "explicit"
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    monkeypatch.chdir(tmp_path)  # cwd irrelevant when env is set

    assert paths.base_dir() == home
    assert paths.config_dir() == home / "config"
    assert paths.data_dir() == home / "data"


def test_repo_local_used_in_development(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)

    assert paths.base_dir() == repo
    assert paths.config_dir() == repo / "config"
    assert paths.data_dir() == repo / "data"


def test_repo_local_detected_by_platform_example(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "checkout"
    repo.mkdir(parents=True)
    (repo / "platform.yaml.example").write_text("knowledge: {}\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    assert paths.base_dir() == repo


def test_home_fallback_when_not_in_repo(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bare = tmp_path / "elsewhere"
    bare.mkdir()
    monkeypatch.chdir(bare)

    assert paths.base_dir() == isolated_home / ".fleetent"
    assert paths.config_dir() == isolated_home / ".fleetent" / "config"
    assert paths.data_dir() == isolated_home / ".fleetent" / "data"


def test_explicit_home_overrides_repo_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path / "repo")
    override = tmp_path / "override"
    monkeypatch.setenv("FLEETENT_HOME", str(override))
    monkeypatch.chdir(repo)

    assert paths.base_dir() == override


def test_derived_paths_under_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "h"
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    assert paths.platform_yaml_path() == home / "platform.yaml"
    assert paths.sessions_dir() == home / "data" / "sessions"


def test_default_agent_file_under_agents_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The default materialized Agent runtime lives under agents/default.
    home = tmp_path / "h"
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    assert paths.agent_file() == home / "agents" / "default" / "agent.yaml"
