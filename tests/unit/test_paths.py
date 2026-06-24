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
    assert paths.management_db_path() == home / "management.db"
    assert paths.logs_dir() == home / "logs"
    assert paths.diagnostics_dir() == home / "diagnostics"
    assert paths.data_dir() == home / "data"
    assert paths.tenant_dir("acme") == home / "tenants" / "acme"


def test_repo_local_used_in_development(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)

    assert paths.base_dir() == repo
    assert paths.management_db_path() == repo / "management.db"
    assert paths.logs_dir() == repo / "logs"
    assert paths.diagnostics_dir() == repo / "diagnostics"
    assert paths.data_dir() == repo / "data"
    assert paths.tenant_dir("default") == repo / "tenants" / "default"


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
    assert paths.management_db_path() == isolated_home / ".fleetent" / "management.db"
    assert paths.logs_dir() == isolated_home / ".fleetent" / "logs"
    assert paths.diagnostics_dir() == isolated_home / ".fleetent" / "diagnostics"
    assert paths.data_dir() == isolated_home / ".fleetent" / "data"
    assert paths.tenant_dir("default") == isolated_home / ".fleetent" / "tenants" / "default"


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
    assert paths.platform_env_path() == home / ".env"
    assert paths.management_db_path() == home / "management.db"
    assert paths.logs_dir() == home / "logs"
    assert paths.diagnostics_dir() == home / "diagnostics"
    assert paths.sessions_dir() == home / "data" / "sessions"


def test_default_agent_file_under_agents_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The default standalone Agent runtime lives under tenants/default/agents/default.
    home = tmp_path / "h"
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    assert paths.agent_file() == home / "tenants" / "default" / "agents" / "default" / "agent.yaml"
    assert paths.tenant_agent_home_dir("acme", "support") == (
        home / "tenants" / "acme" / "agents" / "support"
    )
    assert paths.agent_home_dir("support") == home / "tenants" / "default" / "agents" / "support"


def test_agent_data_dir_derives_from_agents_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "h"
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    assert paths.tenant_agent_data_dir("acme", "my-bot") == (
        home / "tenants" / "acme" / "agents" / "my-bot" / "data"
    )
    assert (
        paths.agent_data_dir("my-bot")
        == home / "tenants" / "default" / "agents" / "my-bot" / "data"
    )


def test_agent_data_dir_injectable_via_monkeypatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        paths, "tenant_agent_home_dir", lambda tenant_id, agent_id: tmp_path / tenant_id / agent_id
    )

    assert paths.tenant_agent_data_dir("tenant-a", "test-agent") == (
        tmp_path / "tenant-a" / "test-agent" / "data"
    )


def test_workspaces_dir_under_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "h"
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    assert paths.workspaces_dir() == home / "data" / "workspaces"


def test_workspaces_dir_injectable_via_monkeypatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)

    assert paths.workspaces_dir() == tmp_path / "workspaces"
