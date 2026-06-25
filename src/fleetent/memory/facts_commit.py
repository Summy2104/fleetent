"""Transactional commit of classified facts into agent_state.db.

All SQL changes for one conversation turn happen inside a single SQLite
transaction so a mid-commit failure rolls back every change.  Vector index
sync runs *after* the transaction commits (see ``sync_vectors``): a vector
write failure is logged but never rolls back persisted facts.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fleetent.db import SQLiteConnection, SQLiteDatabase
from fleetent.memory import facts_store
from fleetent.memory.facts_migrations import LONG_TERM_RELATIONS
from fleetent.memory.facts_models import (
    FORGET_RELATION,
    RENAME_RELATION,
    ClassifiedFact,
    Fact,
)
from fleetent.memory.facts_temporal import temporal_boundary
from fleetent.memory.store import format_datetime
from fleetent.vector_store.namespaces import memory_namespace
from fleetent.vector_store.runtime import embed_text

logger = logging.getLogger(__name__)

# Default short-term lifetime when the LLM detects no explicit time boundary.
DEFAULT_SHORT_TERM_TTL = timedelta(days=30)


def commit_facts(
    user_id: str,
    classified: list[ClassifiedFact],
    db: SQLiteDatabase,
    *,
    source_turn: str | None,
) -> list[Fact]:
    """Apply the state machine for each classified fact in one transaction.

    Returns the list of newly inserted active facts (empty for skip verdicts).
    """
    now = datetime.now(UTC).replace(microsecond=0)
    new_facts: list[Fact] = []

    with db.transaction() as conn:
        for cf in classified:
            if cf.relation == RENAME_RELATION:
                # A rename directive, not a fact: migrate the whole old subject
                # (subject) to the new name (object), then drop the directive.
                _migrate_subject(conn, user_id, cf.subject, cf.object, now, source_turn)
                continue
            if cf.relation == FORGET_RELATION:
                # A forget directive, not a fact: retract the matching fact(s).
                _forget(conn, user_id, cf.subject, cf.object, now)
                continue
            inserted = _commit_one(conn, user_id, cf, now, source_turn)
            if inserted is not None:
                new_facts.append(inserted)

    return new_facts


def _forget(
    conn: SQLiteConnection,
    user_id: str,
    subject: str,
    target_object: str,
    now: datetime,
) -> None:
    """Retract active facts matching a forget directive.

    If ``target_object`` names the subject itself (or is empty), the WHOLE subject
    is forgotten; otherwise only facts whose object matches ``target_object``
    (case/space-insensitive) are retracted.  Retract = soft delete (status
    'retracted', never hard-deleted), so history stays auditable.
    """
    whole_subject = not target_object.strip() or target_object.strip() == subject.strip()
    rows = conn.execute(
        """
        SELECT * FROM facts
        WHERE user_id = :user_id AND subject = :subject AND status = 'active'
        """,
        {"user_id": user_id, "subject": subject},
    ).rows
    target_norm = " ".join(target_object.split()).casefold()
    for row in rows:
        fact = facts_store._row_to_fact(row)
        if whole_subject or " ".join(fact.object.split()).casefold() == target_norm:
            _update_status_in_tx(conn, fact.fact_id, "retracted", now)


def _migrate_subject(
    conn: SQLiteConnection,
    user_id: str,
    old_subject: str,
    new_subject: str,
    now: datetime,
    source_turn: str | None,
) -> None:
    """Archive every active fact under old_subject and re-create it under new_subject.

    Renaming an entity is a subject-level operation: the object-level supersede
    machinery cannot express it, so we move the whole subject's history here.
    """
    if not new_subject.strip() or old_subject == new_subject:
        return
    rows = conn.execute(
        """
        SELECT * FROM facts
        WHERE user_id = :user_id AND subject = :subject AND status = 'active'
        """,
        {"user_id": user_id, "subject": old_subject},
    ).rows
    # Facts the new subject already holds — don't re-create them (idempotent rename;
    # a repeated/duplicate rename directive must not pile up duplicates).
    existing_new = conn.execute(
        """
        SELECT relation, object FROM facts
        WHERE user_id = :user_id AND subject = :subject AND status = 'active'
        """,
        {"user_id": user_id, "subject": new_subject},
    ).rows
    seen = {(r["relation"], " ".join(str(r["object"]).split()).casefold()) for r in existing_new}
    for row in rows:
        old = facts_store._row_to_fact(row)
        _update_status_in_tx(conn, old.fact_id, "archived", now)
        key = (old.relation, " ".join(old.object.split()).casefold())
        if key in seen:
            continue  # new subject already has this fact; archive old, skip re-create
        seen.add(key)
        migrated = Fact(
            fact_id=str(uuid.uuid4()),
            user_id=user_id,
            subject=new_subject,
            relation=old.relation,
            object=old.object,
            cardinality=old.cardinality,
            status="active",
            access_count=0,
            first_accessed_at=None,
            last_accessed_at=None,
            expires_at=old.expires_at,
            valid_until=old.valid_until,
            created_at=now,
            updated_at=now,
            source_turn=source_turn,
            statement=old.statement,
        )
        _insert_fact_in_tx(conn, migrated)


def _commit_one(
    conn: SQLiteConnection,
    user_id: str,
    cf: ClassifiedFact,
    now: datetime,
    source_turn: str | None,
) -> Fact | None:
    """Apply one classified fact's verdict.  Returns the new Fact or None (skipped)."""
    if cf.verdict in ("Equivalent", "NewSubsumed"):
        # New fact adds nothing — skip.
        return None

    existing = _active_facts_in_tx(conn, user_id, cf.subject, cf.relation)

    superseded_ids: list[str] = []
    if cf.cardinality == "single":
        # A single-valued relation: any prior active value is replaced.
        if existing:
            superseded_ids = [f.fact_id for f in existing]
    elif cf.verdict == "Contradict":
        # multi + contradict: supersede only the contradicted (most similar) facts.
        # Without an embedding comparison here we supersede all existing — the
        # classifier already judged a contradiction against the active set.
        superseded_ids = [f.fact_id for f in existing]
    # multi + Orthogonal / Subsumes: coexist, supersede nothing.

    new_fact = _build_fact(user_id, cf, now, source_turn)
    _insert_fact_in_tx(conn, new_fact)

    for old_id in superseded_ids:
        _update_status_in_tx(conn, old_id, "superseded", now)
        _insert_edge_in_tx(conn, new_fact.fact_id, old_id, now)

    return new_fact


def _build_fact(
    user_id: str,
    cf: ClassifiedFact,
    now: datetime,
    source_turn: str | None,
) -> Fact:
    # The LLM gives a temporal-intent label; code computes the actual boundary.
    valid_until = temporal_boundary(cf.temporal, now)
    if valid_until is not None:
        # An explicit time boundary always wins (e.g. "today" → end of today).
        expires_at: datetime | None = valid_until
    elif cf.relation in LONG_TERM_RELATIONS:
        # Stable identity facts are long-term from the start — no expiry.
        expires_at = None
    else:
        expires_at = now + DEFAULT_SHORT_TERM_TTL
    return Fact(
        fact_id=str(uuid.uuid4()),
        user_id=user_id,
        subject=cf.subject,
        relation=cf.relation,
        object=cf.object,
        cardinality=cf.cardinality,
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=expires_at,
        valid_until=valid_until,
        created_at=now,
        updated_at=now,
        source_turn=source_turn,
        statement=cf.statement,
    )


async def sync_vectors(
    user_id: str,
    *,
    new_active: list[Fact],
    superseded_ids: list[str],
    vector_backend: object,
) -> None:
    """Best-effort vector index sync after a committed transaction.

    Upserts each new active fact and deletes superseded ones.  Any failure is
    logged and swallowed — the SQL transaction has already committed, so the
    index can be rebuilt later without losing persisted facts.
    """
    namespace = memory_namespace(user_id)
    backend = vector_backend
    for fact in new_active:
        try:
            vector = await embed_text(_fact_text(fact))
            await backend.upsert(fact.fact_id, vector, namespace)  # type: ignore[attr-defined]
        except Exception:
            logger.warning(
                "facts_commit: vector upsert failed for fact %s", fact.fact_id, exc_info=True
            )
    for old_id in superseded_ids:
        try:
            await backend.delete(old_id, namespace)  # type: ignore[attr-defined]
        except Exception:
            logger.warning("facts_commit: vector delete failed for fact %s", old_id, exc_info=True)


def _fact_text(fact: Fact) -> str:
    """Render a fact triple as the text indexed for semantic retrieval."""
    return f"{fact.subject} {fact.relation} {fact.object}"


# ── in-transaction SQL (operate on the transaction's connection) ──────────────


def _active_facts_in_tx(
    conn: SQLiteConnection, user_id: str, subject: str, relation: str
) -> list[Fact]:
    result = conn.execute(
        """
        SELECT * FROM facts
        WHERE user_id = :user_id AND subject = :subject
          AND relation = :relation AND status = 'active'
        ORDER BY created_at ASC
        """,
        {"user_id": user_id, "subject": subject, "relation": relation},
    )
    return [facts_store._row_to_fact(row) for row in result.rows]


def _insert_fact_in_tx(conn: SQLiteConnection, fact: Fact) -> None:
    conn.execute(
        """
        INSERT INTO facts (
            fact_id, user_id, subject, relation, object, cardinality,
            status, access_count, first_accessed_at, last_accessed_at,
            expires_at, valid_until, created_at, updated_at, source_turn, statement
        )
        VALUES (
            :fact_id, :user_id, :subject, :relation, :object, :cardinality,
            :status, :access_count, :first_accessed_at, :last_accessed_at,
            :expires_at, :valid_until, :created_at, :updated_at, :source_turn, :statement
        )
        """,
        facts_store._fact_params(fact),
    )


def _update_status_in_tx(conn: SQLiteConnection, fact_id: str, status: str, now: datetime) -> None:
    conn.execute(
        "UPDATE facts SET status = :status, updated_at = :now WHERE fact_id = :fact_id",
        {"status": status, "now": format_datetime(now), "fact_id": fact_id},
    )


def _insert_edge_in_tx(
    conn: SQLiteConnection, from_fact_id: str, to_fact_id: str, now: datetime
) -> None:
    conn.execute(
        """
        INSERT INTO fact_edges (edge_id, from_fact_id, to_fact_id, edge_type, created_at)
        VALUES (:edge_id, :from_fact_id, :to_fact_id, 'supersedes', :created_at)
        """,
        {
            "edge_id": str(uuid.uuid4()),
            "from_fact_id": from_fact_id,
            "to_fact_id": to_fact_id,
            "created_at": format_datetime(now),
        },
    )
