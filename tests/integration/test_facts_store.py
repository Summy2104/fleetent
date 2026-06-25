"""Integration tests: facts_store SQL access layer."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS


def _open_db(tmp_path: Path) -> SQLiteDatabase:
    db_path = tmp_path / "agent_state.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


# ── inject DB guard ───────────────────────────────────────────────────────────


def test_insert_fact_raises_without_set_facts_db() -> None:
    from fleetent.memory import facts_store

    facts_store._facts_db = None
    with pytest.raises(RuntimeError, match="set_facts_db"):
        facts_store._facts_database()


# ── insert_fact ───────────────────────────────────────────────────────────────


def test_insert_fact_success(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    fact = Fact(
        fact_id="f1",
        user_id="u1",
        subject="user",
        relation="is_role",
        object="developer",
        cardinality="single",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )
    facts_store.insert_fact(fact)
    retrieved = facts_store.get_fact("f1")
    assert retrieved is not None
    assert retrieved.relation == "is_role"
    assert retrieved.object == "developer"


def test_insert_fact_duplicate_id_raises(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    fact = Fact(
        fact_id="dup",
        user_id="u1",
        subject="user",
        relation="is_role",
        object="dev",
        cardinality="single",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )
    facts_store.insert_fact(fact)
    with pytest.raises(Exception):  # sqlite3 IntegrityError
        facts_store.insert_fact(fact)


# ── update_fact_status ────────────────────────────────────────────────────────


def test_update_fact_status(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    fact = Fact(
        fact_id="f2",
        user_id="u1",
        subject="user",
        relation="is_role",
        object="dev",
        cardinality="single",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )
    facts_store.insert_fact(fact)
    facts_store.update_fact_status("f2", "superseded")
    updated = facts_store.get_fact("f2")
    assert updated is not None
    assert updated.status == "superseded"


# ── facts_by_ids ──────────────────────────────────────────────────────────────


def test_facts_by_ids(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()

    def _mk(fid: str, obj: str) -> Fact:
        return Fact(
            fact_id=fid,
            user_id="u1",
            subject="user",
            relation="has_skill",
            object=obj,
            cardinality="multi",
            status="active",
            access_count=0,
            first_accessed_at=None,
            last_accessed_at=None,
            expires_at=None,
            valid_until=None,
            created_at=now,
            updated_at=now,
            source_turn=None,
        )

    for fid, obj in [("a", "Python"), ("b", "Rust"), ("c", "Go")]:
        facts_store.insert_fact(_mk(fid, obj))

    result = facts_store.facts_by_ids(["a", "c"])
    assert set(result.keys()) == {"a", "c"}
    assert result["a"].object == "Python"


# ── active_facts_for_relation ─────────────────────────────────────────────────


def test_active_facts_for_relation(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()

    def _mk(fid: str, status: str, obj: str) -> Fact:
        return Fact(
            fact_id=fid,
            user_id="u1",
            subject="user",
            relation="has_skill",
            object=obj,
            cardinality="multi",
            status=status,  # type: ignore[arg-type]
            access_count=0,
            first_accessed_at=None,
            last_accessed_at=None,
            expires_at=None,
            valid_until=None,
            created_at=now,
            updated_at=now,
            source_turn=None,
        )

    facts_store.insert_fact(_mk("act1", "active", "Python"))
    facts_store.insert_fact(_mk("sup1", "superseded", "Java"))
    facts_store.insert_fact(_mk("act2", "active", "Rust"))

    active = facts_store.active_facts_for_relation("u1", "user", "has_skill")
    ids = {f.fact_id for f in active}
    assert ids == {"act1", "act2"}
    assert "sup1" not in ids


# ── insert_fact_edge / get_supersedes_chain ───────────────────────────────────


def test_insert_fact_edge(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact, FactEdge

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()

    def _mk(fid: str) -> Fact:
        return Fact(
            fact_id=fid,
            user_id="u1",
            subject="user",
            relation="is_role",
            object="dev",
            cardinality="single",
            status="active",
            access_count=0,
            first_accessed_at=None,
            last_accessed_at=None,
            expires_at=None,
            valid_until=None,
            created_at=now,
            updated_at=now,
            source_turn=None,
        )

    facts_store.insert_fact(_mk("old"))
    facts_store.insert_fact(_mk("new"))
    edge = FactEdge(
        edge_id="e1",
        from_fact_id="new",
        to_fact_id="old",
        edge_type="supersedes",
        created_at=now,
    )
    facts_store.insert_fact_edge(edge)
    chain = facts_store.get_supersedes_chain("new")
    assert len(chain) == 1
    assert chain[0].to_fact_id == "old"


# ── relation_clusters CRUD ────────────────────────────────────────────────────


def test_get_relation_cluster_exact_match(tmp_path: Path) -> None:
    from fleetent.memory import facts_store

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]

    rc = facts_store.get_relation_cluster("is_role")
    assert rc is not None
    assert rc.cardinality == "single"


def test_get_relation_cluster_not_found(tmp_path: Path) -> None:
    from fleetent.memory import facts_store

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]

    rc = facts_store.get_relation_cluster("nonexistent_relation_xyz")
    assert rc is None


def test_insert_relation_cluster(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import RelationCluster

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    rc = RelationCluster(relation="mentors", cardinality="multi", embedding=None, created_at=now)
    facts_store.insert_relation_cluster(rc)

    retrieved = facts_store.get_relation_cluster("mentors")
    assert retrieved is not None
    assert retrieved.cardinality == "multi"


def test_list_relation_clusters(tmp_path: Path) -> None:
    from fleetent.memory import facts_store

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]

    clusters = facts_store.list_relation_clusters()
    relations = {rc.relation for rc in clusters}
    assert "is_role" in relations
    assert "has_skill" in relations


# ── update_fact_access ────────────────────────────────────────────────────────


def test_update_fact_access_increments_count(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    fact = Fact(
        fact_id="acc1",
        user_id="u1",
        subject="user",
        relation="is_role",
        object="dev",
        cardinality="single",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )
    facts_store.insert_fact(fact)
    facts_store.update_fact_access("acc1", now)

    updated = facts_store.get_fact("acc1")
    assert updated is not None
    assert updated.access_count == 1
    assert updated.last_accessed_at is not None
    assert updated.first_accessed_at is not None


def test_update_fact_access_first_accessed_at_only_set_once(tmp_path: Path) -> None:
    from fleetent.memory import facts_store
    from fleetent.memory.facts_models import Fact

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    now = _now()
    fact = Fact(
        fact_id="acc2",
        user_id="u1",
        subject="user",
        relation="is_role",
        object="dev",
        cardinality="single",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )
    facts_store.insert_fact(fact)
    facts_store.update_fact_access("acc2", now)
    later = now + timedelta(days=1)
    facts_store.update_fact_access("acc2", later)

    updated = facts_store.get_fact("acc2")
    assert updated is not None
    assert updated.access_count == 2
    # first_accessed_at must still be the original `now`
    assert updated.first_accessed_at == now
    assert updated.last_accessed_at == later
