"""DB and session path constants derive from the central resolver."""

import importlib
from pathlib import Path

import pytest

from fleetent import paths, user_store
from fleetent.session import index as session_index
from fleetent.session import manager as session_manager


def test_db_and_session_constants_derive_from_paths() -> None:
    # Names are preserved (no rename): fleetent.db / users.db / sessions.
    assert paths.data_dir() / "fleetent.db" == user_store.DB_PATH
    assert paths.data_dir() / "users.db" == session_index.DB_PATH
    assert paths.data_dir() / "sessions" == session_manager.SESSIONS_DIR


def test_session_paths_redirect_on_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    reloaded = importlib.reload(session_manager)
    try:
        assert tmp_path / "data" / "sessions" == reloaded.SESSIONS_DIR
    finally:
        monkeypatch.delenv("FLEETENT_HOME", raising=False)
        importlib.reload(session_manager)
