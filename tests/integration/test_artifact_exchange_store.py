"""Integration: artifact_exchange ledger store (register / get / list_by_session)."""

from __future__ import annotations

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture
def ledger_db(tmp_path, monkeypatch):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    monkeypatch.setattr(artifact_exchange, "_state_db", db)
    return db


def test_register_then_get_roundtrip(ledger_db):
    aid = artifact_exchange.register(
        server_id="google-drive",
        rel_path="reports/q3.xlsx",
        session_id="slack:C1:170.5",
        user_id="U1",
        filename="q3.xlsx",
        mime="application/vnd.ms-excel",
        size=2048,
    )
    art = artifact_exchange.get(aid)
    assert art is not None
    assert art.server_id == "google-drive"
    assert art.rel_path == "reports/q3.xlsx"
    assert art.session_id == "slack:C1:170.5"
    assert art.filename == "q3.xlsx"
    assert art.size == 2048


def test_list_by_session_filters(ledger_db):
    artifact_exchange.register(
        server_id="gd", rel_path="a.txt", session_id="S1", user_id="U", filename="a.txt"
    )
    artifact_exchange.register(
        server_id="gd", rel_path="b.txt", session_id="S1", user_id="U", filename="b.txt"
    )
    artifact_exchange.register(
        server_id="gd", rel_path="c.txt", session_id="S2", user_id="U", filename="c.txt"
    )
    s1 = artifact_exchange.list_by_session("S1")
    assert {a.rel_path for a in s1} == {"a.txt", "b.txt"}


def test_reregister_same_path_is_idempotent(ledger_db):
    aid1 = artifact_exchange.register(
        server_id="gd", rel_path="x.txt", session_id="S1", user_id="U", filename="x.txt", size=1
    )
    aid2 = artifact_exchange.register(
        server_id="gd", rel_path="x.txt", session_id="S1", user_id="U", filename="x.txt", size=99
    )
    assert aid1 == aid2
    # metadata refreshed, no duplicate row
    assert len(artifact_exchange.list_by_session("S1")) == 1
    assert artifact_exchange.get(aid1).size == 99
