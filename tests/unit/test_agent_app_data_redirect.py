"""Unit tests for _redirect_agent_data_paths: per-agent data path wiring in boot()."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_redirect_sets_sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.runtime import agent_app
    from fleetent.session import manager as session_mgr

    home = tmp_path / "myagent"
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", session_mgr.SESSIONS_DIR)
    # Ensure DATABASE_URL set by _redirect_agent_data_paths is cleaned up on teardown.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    agent_app._redirect_agent_data_paths(home)

    assert session_mgr.SESSIONS_DIR == home / "data" / "sessions"


def test_redirect_sets_approvals_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.im_gateway import access
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(access, "APPROVALS_PATH", access.APPROVALS_PATH)
    monkeypatch.delenv("DATABASE_URL", raising=False)

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
    monkeypatch.setenv("DATABASE_URL", "postgresql://custom-explicit")

    agent_app._redirect_agent_data_paths(home)

    assert os.environ["DATABASE_URL"] == "postgresql://custom-explicit"


def test_redirect_updates_diagnostics_default_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.observability import diagnostics
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(diagnostics, "_default_data_dir", diagnostics._default_data_dir)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    agent_app._redirect_agent_data_paths(home)

    assert diagnostics._default_data_dir() == home / "data"
