"""agent-runtime-db-routing-cleanup: reflection must not fall back to the management DB
(Settings().database_url) when no per-agent _state_db is injected. Without injection it
refuses rather than creating/writing reflection-owned tables in the shared management
library."""

import pytest

from fleetent.config import Settings
from fleetent.db import create_database


def test_reflection_database_refuses_without_state_injection(monkeypatch):
    from fleetent import reflection

    monkeypatch.setattr(reflection, "_state_db", None)
    mgmt_path = create_database(Settings().database_url).path

    # No fallback to the management DB: the accessor refuses instead of returning a
    # handle on Settings().database_url.
    with pytest.raises(RuntimeError):
        reflection._database()  # noqa: SLF001 — guarding the private fallback branch

    assert not _has_reflection_tables(mgmt_path)


def test_list_skill_proposals_refuses_without_state_injection(monkeypatch):
    from fleetent import reflection

    monkeypatch.setattr(reflection, "_state_db", None)
    mgmt_path = create_database(Settings().database_url).path

    with pytest.raises(RuntimeError):
        reflection.list_skill_proposals("pending")

    assert not _has_reflection_tables(mgmt_path)


def _has_reflection_tables(db_path) -> bool:
    import sqlite3

    if not db_path.exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('reflection_reports', 'reflection_proposals')"
        ).fetchall()
        return bool(rows)
    finally:
        conn.close()
