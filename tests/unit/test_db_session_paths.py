"""DB and session path constants derive from the central resolver."""

import importlib
from pathlib import Path

import pytest

from fleetent.session import index as session_index
from fleetent.session import manager as session_manager


def _assert_derivation_in_clean_env(code: str) -> None:
    """Run an import-time derivation assertion in a child interpreter.

    Constants are frozen at import. Comparing an in-process constant against a
    call-time paths.X() is fragile: an ambient FLEETENT_HOME in the developer
    shell freezes a different base than a post-delenv call resolves. A child
    interpreter with FLEETENT_HOME stripped checks constant == derivation under
    one consistent environment.
    """
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "FLEETENT_HOME"}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_db_and_session_constants_derive_from_paths() -> None:
    _assert_derivation_in_clean_env(
        "from fleetent import paths, user_store; "
        "from fleetent.session import manager as session_manager; "
        "assert user_store.DB_PATH == paths.management_db_path(), user_store.DB_PATH; "
        "assert session_manager.SESSIONS_DIR == paths.data_dir() / 'sessions'"
    )
    # session/index.py migrated away from users.db; it no longer exposes DB_PATH.
    # Verify it uses db.py (create_database) instead of the old sqlite3 path constant.
    assert not hasattr(session_index, "DB_PATH"), (
        "session.index must not expose DB_PATH after migration to db.py"
    )


def test_session_paths_redirect_on_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    reloaded = importlib.reload(session_manager)
    try:
        assert tmp_path / "data" / "sessions" == reloaded.SESSIONS_DIR
    finally:
        monkeypatch.delenv("FLEETENT_HOME", raising=False)
        importlib.reload(session_manager)
