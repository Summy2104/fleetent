"""DB and session path constants derive from the central resolver."""

import importlib
from pathlib import Path

import pytest

from fleetent import paths, user_store
from fleetent.session import index as session_index
from fleetent.session import manager as session_manager


def test_db_and_session_constants_derive_from_paths(monkeypatch) -> None:
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    assert paths.data_dir() / "fleetent.db" == user_store.DB_PATH
    # session/index.py migrated away from users.db; it no longer exposes DB_PATH.
    # Verify it uses db.py (create_database) instead of the old sqlite3 path constant.
    assert not hasattr(session_index, "DB_PATH"), (
        "session.index must not expose DB_PATH after migration to db.py"
    )
    assert paths.data_dir() / "sessions" == session_manager.SESSIONS_DIR


def test_session_paths_redirect_on_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    reloaded = importlib.reload(session_manager)
    try:
        assert tmp_path / "data" / "sessions" == reloaded.SESSIONS_DIR
    finally:
        monkeypatch.delenv("FLEETENT_HOME", raising=False)
        importlib.reload(session_manager)
