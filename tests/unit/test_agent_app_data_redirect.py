"""Unit tests for _redirect_agent_data_paths: per-agent data path wiring in boot()."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_redirect_sets_sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.runtime import agent_app
    from fleetent.session import manager as session_mgr

    home = tmp_path / "myagent"
    # Register cleanup so session_mgr.SESSIONS_DIR is restored after the test.
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", session_mgr.SESSIONS_DIR)

    agent_app._redirect_agent_data_paths(home)

    assert session_mgr.SESSIONS_DIR == home / "data" / "sessions"


def test_redirect_sets_approvals_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.im_gateway import access
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(access, "APPROVALS_PATH", access.APPROVALS_PATH)

    agent_app._redirect_agent_data_paths(home)

    assert access.APPROVALS_PATH == home / "data" / "im_approvals.json"


def test_redirect_sets_database_url_when_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.delenv("DATABASE_URL", raising=False)

    agent_app._redirect_agent_data_paths(home)

    # Pop immediately to prevent env leak across tests.
    db_url = os.environ.pop("DATABASE_URL", None)
    assert db_url == f"sqlite:///{home / 'data' / 'fleetent.db'}"


def test_redirect_does_not_override_explicit_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom/path.db")

    agent_app._redirect_agent_data_paths(home)

    assert os.environ["DATABASE_URL"] == "sqlite:///custom/path.db"


def test_redirect_updates_diagnostics_default_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.observability import diagnostics
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(diagnostics, "_default_data_dir", diagnostics._default_data_dir)

    agent_app._redirect_agent_data_paths(home)

    assert diagnostics._default_data_dir() == home / "data"
