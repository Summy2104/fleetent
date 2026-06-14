"""Integration: artifact_exchange ledger store (register / get / list_by_scope), scope_key axis."""

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
        scope_key="slack:dm:U1:170.5",
        session_id="slack:dm:U1:170.5",
        user_id="U1",
        filename="q3.xlsx",
        mime="application/vnd.ms-excel",
        size=2048,
    )
    art = artifact_exchange.get(aid)
    assert art is not None
    assert art.server_id == "google-drive"
    assert art.rel_path == "reports/q3.xlsx"
    assert art.scope_key == "slack:dm:U1:170.5"
    assert art.session_id == "slack:dm:U1:170.5"  # audit column
    assert art.user_id == "U1"
    assert art.filename == "q3.xlsx"
    assert art.size == 2048


def test_list_by_scope_filters(ledger_db):
    artifact_exchange.register(
        server_id="gd", rel_path="a.txt", scope_key="K1", session_id="S1", filename="a.txt"
    )
    artifact_exchange.register(
        server_id="gd", rel_path="b.txt", scope_key="K1", session_id="S1", filename="b.txt"
    )
    artifact_exchange.register(
        server_id="gd", rel_path="c.txt", scope_key="K2", session_id="S2", filename="c.txt"
    )
    k1 = artifact_exchange.list_by_scope("K1")
    assert {a.rel_path for a in k1} == {"a.txt", "b.txt"}


def test_reregister_same_path_same_scope_is_idempotent(ledger_db):
    aid1 = artifact_exchange.register(
        server_id="gd", rel_path="x.txt", scope_key="K1", session_id="S1", filename="x.txt", size=1
    )
    aid2 = artifact_exchange.register(
        server_id="gd", rel_path="x.txt", scope_key="K1", session_id="S1", filename="x.txt", size=99
    )
    assert aid1 == aid2
    # metadata refreshed, no duplicate row
    assert len(artifact_exchange.list_by_scope("K1")) == 1
    assert artifact_exchange.get(aid1).size == 99


def test_same_path_distinct_scopes_coexist(ledger_db):
    """D4: same (server_id, rel_path) under two scopes are distinct rows; scope-filtered
    lookup returns the requester's own, never 'newest across scopes'."""
    a1 = artifact_exchange.register(
        server_id="gd", rel_path="x.txt", scope_key="K1", session_id="S1", filename="x.txt"
    )
    a2 = artifact_exchange.register(
        server_id="gd", rel_path="x.txt", scope_key="K2", session_id="S2", filename="x.txt"
    )
    assert a1 != a2
    assert artifact_exchange._find_by_path("gd", "x.txt", "K1").artifact_id == a1
    assert artifact_exchange._find_by_path("gd", "x.txt", "K2").artifact_id == a2
    assert {a.scope_key for a in artifact_exchange.list_by_scope("K1")} == {"K1"}
