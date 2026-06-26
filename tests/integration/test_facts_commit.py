"""Integration tests: commit_facts state machine and transaction atomicity."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.memory import facts_store
from fleetent.memory.facts_models import ClassifiedFact, Fact
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _seed_fact(fid: str, relation: str, obj: str, cardinality: str) -> Fact:
    now = _now()
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation=relation,
        object=obj,
        cardinality=cardinality,  # type: ignore[arg-type]
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


def test_single_contradict_supersedes_old(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact("old", "is_role", "Java developer", "single"))

    classified = ClassifiedFact(
        subject="user",
        relation="is_role",
        object="Go developer",
        temporal="none",
        cardinality="single",
        verdict="Contradict",
    )
    new_facts = facts_commit.commit_facts("u1", [classified], db, source_turn="t1")

    assert len(new_facts) == 1
    old = facts_store.get_fact("old")
    assert old is not None and old.status == "superseded"
    new = facts_store.get_fact(new_facts[0].fact_id)
    assert new is not None and new.status == "active"
    chain = facts_store.get_supersedes_chain(new_facts[0].fact_id)
    assert len(chain) == 1
    assert chain[0].to_fact_id == "old"


def test_multi_orthogonal_coexists(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact("py", "has_skill", "Python", "multi"))

    classified = ClassifiedFact(
        subject="user",
        relation="has_skill",
        object="Rust",
        temporal="none",
        cardinality="multi",
        verdict="Orthogonal",
    )
    facts_commit.commit_facts("u1", [classified], db, source_turn="t1")

    active = facts_store.active_facts_for_relation("u1", "user", "has_skill")
    objects = {f.object for f in active}
    assert objects == {"Python", "Rust"}


def test_equivalent_skips_insert(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact("py", "has_skill", "Python", "multi"))

    classified = ClassifiedFact(
        subject="user",
        relation="has_skill",
        object="Python programming",
        temporal="none",
        cardinality="multi",
        verdict="Equivalent",
    )
    new_facts = facts_commit.commit_facts("u1", [classified], db, source_turn="t1")

    assert new_facts == []
    active = facts_store.active_facts_for_relation("u1", "user", "has_skill")
    assert len(active) == 1


def test_transaction_rollback_on_error(tmp_path: Path, monkeypatch) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact("old", "is_role", "Java developer", "single"))

    classified = ClassifiedFact(
        subject="user",
        relation="is_role",
        object="Go developer",
        temporal="none",
        cardinality="single",
        verdict="Contradict",
    )

    # Force a failure midway through the transaction.
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(facts_commit, "_insert_edge_in_tx", _boom)

    with pytest.raises(RuntimeError, match="boom"):
        facts_commit.commit_facts("u1", [classified], db, source_turn="t1")

    # Old fact must remain active — the whole transaction rolled back.
    old = facts_store.get_fact("old")
    assert old is not None and old.status == "active"
    # No new fact persisted.
    active = facts_store.active_facts_for_relation("u1", "user", "is_role")
    assert {f.object for f in active} == {"Java developer"}


def test_commit_persists_statement(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]

    classified = ClassifiedFact(
        subject="user",
        relation="name",
        object="Xin",
        temporal="none",
        cardinality="single",
        verdict="Orthogonal",
        statement="用户的名字是 Xin",
    )
    new_facts = facts_commit.commit_facts("u1", [classified], db, source_turn="t1")

    stored = facts_store.get_fact(new_facts[0].fact_id)
    assert stored is not None
    assert stored.statement == "用户的名字是 Xin"


def test_identity_relation_is_long_term_on_write(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]

    classified = ClassifiedFact(
        subject="user",
        relation="name",
        object="Xin",
        temporal="none",
        cardinality="single",
        verdict="Orthogonal",
        statement="用户的名字是 Xin",
    )
    new_facts = facts_commit.commit_facts("u1", [classified], db, source_turn="t1")

    stored = facts_store.get_fact(new_facts[0].fact_id)
    assert stored is not None
    # Identity facts are long-term immediately: no expiry.
    assert stored.expires_at is None


def test_preference_relation_is_short_term_on_write(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]

    classified = ClassifiedFact(
        subject="user",
        relation="prefers_language",
        object="Python",
        temporal="none",
        cardinality="multi",
        verdict="Orthogonal",
        statement="用户喜欢 Python",
    )
    new_facts = facts_commit.commit_facts("u1", [classified], db, source_turn="t1")

    stored = facts_store.get_fact(new_facts[0].fact_id)
    assert stored is not None
    # Preference facts stay short-term (default 30-day TTL).
    assert stored.expires_at is not None


def _seed_fact_subject(fid: str, subject: str, relation: str, obj: str) -> Fact:
    now = _now()
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject=subject,
        relation=relation,
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


def test_renamed_to_migrates_whole_subject(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    # 张三 has two facts.
    facts_store.insert_fact(_seed_fact_subject("z1", "张三", "works_at", "Northstar"))
    facts_store.insert_fact(_seed_fact_subject("z2", "张三", "slack_id", "U09M"))

    # "张三 renamed_to 张洋" — a rename directive, not a stored fact.
    rename = ClassifiedFact(
        subject="张三",
        relation="renamed_to",
        object="张洋",
        temporal="none",
        cardinality="single",
        verdict="Orthogonal",
        statement="张三改名为张洋",
    )
    facts_commit.commit_facts("u1", [rename], db, source_turn="t1")

    # Old subject 张三 fully archived.
    old = facts_store.active_facts_for_relation("u1", "张三", "works_at")
    assert old == []
    assert facts_store.active_facts_for_relation("u1", "张三", "slack_id") == []
    # New subject 张洋 carries the same facts.
    zy_work = facts_store.active_facts_for_relation("u1", "张洋", "works_at")
    zy_id = facts_store.active_facts_for_relation("u1", "张洋", "slack_id")
    assert {f.object for f in zy_work} == {"Northstar"}
    assert {f.object for f in zy_id} == {"U09M"}
    # The renamed_to row itself is NOT stored as a fact.
    assert facts_store.active_facts_for_relation("u1", "张三", "renamed_to") == []
    assert facts_store.active_facts_for_relation("u1", "张洋", "renamed_to") == []


def test_forget_specific_object_retracts_one_fact(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact_subject("p1", "user", "prefers_language", "Python"))
    facts_store.insert_fact(_seed_fact_subject("t1", "user", "prefers_language", "TypeScript"))

    # "忘记我喜欢 Python" → forget the matching object only.
    forget = ClassifiedFact(
        subject="user",
        relation="forget",
        object="Python",
        temporal="none",
        cardinality="single",
        verdict="Orthogonal",
        statement="用户要求忘记喜欢 Python",
    )
    facts_commit.commit_facts("u1", [forget], db, source_turn="t1")

    active = facts_store.active_facts_for_relation("u1", "user", "prefers_language")
    # Only Python retracted; TypeScript stays.
    assert {f.object for f in active} == {"TypeScript"}
    py = facts_store.get_fact("p1")
    assert py is not None and py.status == "retracted"
    # forget directive itself is not stored.
    assert facts_store.active_facts_for_relation("u1", "user", "forget") == []


def test_forget_whole_subject_retracts_all(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact_subject("z1", "张三", "works_at", "Northstar"))
    facts_store.insert_fact(_seed_fact_subject("z2", "张三", "slack_id", "U09M"))

    # "忘记张三" / "删掉张三" — object names the subject itself → forget the whole subject.
    forget = ClassifiedFact(
        subject="张三",
        relation="forget",
        object="张三",
        temporal="none",
        cardinality="single",
        verdict="Orthogonal",
        statement="用户要求删除张三的所有记忆",
    )
    facts_commit.commit_facts("u1", [forget], db, source_turn="t1")

    assert facts_store.active_facts_for_relation("u1", "张三", "works_at") == []
    assert facts_store.active_facts_for_relation("u1", "张三", "slack_id") == []


def test_rename_migration_dedupes_against_existing_new_subject(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    # 张洋 already has works_at=Northstar; 张三 (to be renamed) has the same fact.
    facts_store.insert_fact(_seed_fact_subject("zy1", "张洋", "works_at", "Northstar"))
    facts_store.insert_fact(_seed_fact_subject("zs1", "张三", "works_at", "Northstar"))
    facts_store.insert_fact(_seed_fact_subject("zs2", "张三", "slack_id", "U09M"))

    rename = ClassifiedFact(
        subject="张三",
        relation="renamed_to",
        object="张洋",
        temporal="none",
        cardinality="single",
        verdict="Orthogonal",
        statement="张三改名为张洋",
    )
    facts_commit.commit_facts("u1", [rename], db, source_turn="t1")

    # 张洋 must NOT have a duplicate works_at=Northstar; just one, plus the new slack_id.
    work = facts_store.active_facts_for_relation("u1", "张洋", "works_at")
    assert [f.object for f in work] == ["Northstar"]  # not duplicated
    sid = facts_store.active_facts_for_relation("u1", "张洋", "slack_id")
    assert {f.object for f in sid} == {"U09M"}
    # 张三 fully archived.
    assert facts_store.active_facts_for_relation("u1", "张三", "works_at") == []


def test_single_relation_overrides_despite_equivalent_verdict(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact_subject("old", "agent", "name", "AI 助手"))
    # Force the old (multi) cardinality to single to mirror the name relation.
    facts_store.update_fact_status("old", "active")  # ensure active
    # Re-insert as single is simpler: clear and add a single one.
    db.execute("UPDATE facts SET cardinality='single' WHERE fact_id='old'")

    # LLM misjudges a clearly-different new name as Equivalent. For a single
    # relation the new value must STILL override the old (deterministic).
    cf = ClassifiedFact(
        subject="agent",
        relation="name",
        object="Fleetent",
        temporal="none",
        cardinality="single",
        verdict="Equivalent",  # wrong verdict from the LLM
        statement="助手叫 Fleetent",
    )
    new_facts = facts_commit.commit_facts("u1", [cf], db, source_turn="t1")

    assert len(new_facts) == 1  # new name was stored despite Equivalent verdict
    old = facts_store.get_fact("old")
    assert old is not None and old.status == "superseded"
    active = facts_store.active_facts_for_relation("u1", "agent", "name")
    assert {f.object for f in active} == {"Fleetent"}


def test_single_relation_same_value_still_skips(tmp_path: Path) -> None:
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact_subject("old", "agent", "name", "Fleetent"))
    db.execute("UPDATE facts SET cardinality='single' WHERE fact_id='old'")

    # Same value (case/space-insensitive) → no new row, old stays.
    cf = ClassifiedFact(
        subject="agent", relation="name", object=" fleetent ",
        temporal="none", cardinality="single", verdict="Orthogonal",
        statement="助手叫 Fleetent",
    )
    new_facts = facts_commit.commit_facts("u1", [cf], db, source_turn="t1")

    assert new_facts == []  # identical value → skipped
    active = facts_store.active_facts_for_relation("u1", "agent", "name")
    assert {f.object for f in active} == {"Fleetent"}
    assert facts_store.get_fact("old").status == "active"
