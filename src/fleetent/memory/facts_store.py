"""SQLite access for user memory facts.

Connection source: the per-agent agent_state.db obtained via agent_scope in
agent_app._init_agent_db_schema.  Call ``set_facts_db(db, vector_backend)``
once at agent boot before any reads or writes.  Agent isolation is physical
(one DB per agent); no namespace column is used.
"""

from __future__ import annotations

from datetime import datetime

from fleetent.db import SQLiteDatabase
from fleetent.memory.facts_models import (
    Cardinality,
    Fact,
    FactEdge,
    FactStatus,
    RelationCluster,
)
from fleetent.memory.store import format_datetime, parse_datetime, parse_optional_datetime
from fleetent.vector_store.backend import VectorBackend

_facts_db: SQLiteDatabase | None = None
_facts_vector_backend: VectorBackend | None = None


def set_facts_db(db: SQLiteDatabase, vector_backend: VectorBackend | None) -> None:
    """Inject the per-agent facts DB and vector backend.  Called once at boot."""
    global _facts_db, _facts_vector_backend
    _facts_db = db
    _facts_vector_backend = vector_backend


def _facts_database() -> SQLiteDatabase:
    if _facts_db is None:
        raise RuntimeError(
            "memory/facts_store: facts_db not initialized — call set_facts_db(db, backend) at boot"
        )
    return _facts_db


def _facts_vector() -> VectorBackend:
    if _facts_vector_backend is None:
        raise RuntimeError(
            "memory/facts_store: facts_vector_backend not initialized"
            " — call set_facts_db(db, backend) at boot"
        )
    return _facts_vector_backend


# ── facts CRUD ────────────────────────────────────────────────────────────────


def insert_fact(fact: Fact) -> None:
    """Insert one fact row.  Raises on duplicate fact_id."""
    _facts_database().execute(
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
        _fact_params(fact),
    )


def update_fact_status(fact_id: str, status: FactStatus) -> None:
    """Update a fact's status and bump updated_at to now (caller-provided)."""
    _facts_database().execute(
        """
        UPDATE facts
        SET status = :status,
            updated_at = :updated_at
        WHERE fact_id = :fact_id
        """,
        {
            "fact_id": fact_id,
            "status": status,
            "updated_at": _now_iso(),
        },
    )


def set_fact_expires_at(fact_id: str, expires_at: datetime | None) -> None:
    """Set a fact's expires_at (NULL = long-term) and bump updated_at."""
    _facts_database().execute(
        """
        UPDATE facts
        SET expires_at = :expires_at,
            updated_at = :updated_at
        WHERE fact_id = :fact_id
        """,
        {
            "fact_id": fact_id,
            "expires_at": format_datetime(expires_at),
            "updated_at": _now_iso(),
        },
    )


def get_fact(fact_id: str) -> Fact | None:
    """Load one fact by id, or None if it does not exist."""
    row = (
        _facts_database()
        .execute("SELECT * FROM facts WHERE fact_id = :fact_id", {"fact_id": fact_id})
        .fetchone()
    )
    return _row_to_fact(row) if row is not None else None


def facts_by_ids(ids: list[str]) -> dict[str, Fact]:
    """Load multiple facts by id, returning a {fact_id: Fact} map."""
    if not ids:
        return {}
    placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
    params: dict[str, object] = {f"id_{index}": fid for index, fid in enumerate(ids)}
    rows = (
        _facts_database()
        .execute(f"SELECT * FROM facts WHERE fact_id IN ({placeholders})", params)
        .fetchall()
    )
    return {str(row["fact_id"]): _row_to_fact(row) for row in rows}


def active_facts_for_relation(user_id: str, subject: str, relation: str) -> list[Fact]:
    """Return active facts for a given user + subject + relation."""
    rows = (
        _facts_database()
        .execute(
            """
            SELECT * FROM facts
            WHERE user_id = :user_id
              AND subject = :subject
              AND relation = :relation
              AND status = 'active'
            ORDER BY created_at ASC
            """,
            {"user_id": user_id, "subject": subject, "relation": relation},
        )
        .fetchall()
    )
    return [_row_to_fact(row) for row in rows]


def list_active_facts(user_id: str, subject: str | None = None) -> list[Fact]:
    """Return ALL active facts for a user_id (optionally one subject), no limit.

    Full enumeration for "show me everything" recall — distinct from
    active_facts_for_relation (one relation) and search_facts (semantic top-N).
    Pure read: no vector search, no access-count side effects, no truncation.
    """
    clauses = ["user_id = :user_id", "status = 'active'"]
    params: dict[str, object] = {"user_id": user_id}
    if subject is not None:
        clauses.append("subject = :subject")
        params["subject"] = subject
    rows = (
        _facts_database()
        .execute(
            f"SELECT * FROM facts WHERE {' AND '.join(clauses)} ORDER BY created_at ASC",
            params,
        )
        .fetchall()
    )
    return [_row_to_fact(row) for row in rows]


def update_fact_access(fact_id: str, accessed_at: datetime) -> None:
    """Increment access_count, set last_accessed_at, set first_accessed_at once."""
    _facts_database().execute(
        """
        UPDATE facts
        SET access_count = access_count + 1,
            last_accessed_at = :accessed_at,
            first_accessed_at = COALESCE(first_accessed_at, :accessed_at),
            updated_at = :accessed_at
        WHERE fact_id = :fact_id
        """,
        {"fact_id": fact_id, "accessed_at": format_datetime(accessed_at)},
    )


# ── fact_edges ────────────────────────────────────────────────────────────────


def insert_fact_edge(edge: FactEdge) -> None:
    """Insert one supersedes edge."""
    _facts_database().execute(
        """
        INSERT INTO fact_edges (edge_id, from_fact_id, to_fact_id, edge_type, created_at)
        VALUES (:edge_id, :from_fact_id, :to_fact_id, :edge_type, :created_at)
        """,
        {
            "edge_id": edge.edge_id,
            "from_fact_id": edge.from_fact_id,
            "to_fact_id": edge.to_fact_id,
            "edge_type": edge.edge_type,
            "created_at": format_datetime(edge.created_at),
        },
    )


def get_supersedes_chain(from_fact_id: str) -> list[FactEdge]:
    """Return edges originating from a fact (its direct supersedes targets)."""
    rows = (
        _facts_database()
        .execute(
            "SELECT * FROM fact_edges WHERE from_fact_id = :fid ORDER BY created_at ASC",
            {"fid": from_fact_id},
        )
        .fetchall()
    )
    return [_row_to_edge(row) for row in rows]


# ── relation_clusters ─────────────────────────────────────────────────────────


def get_relation_cluster(relation: str) -> RelationCluster | None:
    """Load one relation cluster by exact relation name, or None."""
    row = (
        _facts_database()
        .execute(
            "SELECT * FROM relation_clusters WHERE relation = :relation",
            {"relation": relation},
        )
        .fetchone()
    )
    return _row_to_cluster(row) if row is not None else None


def insert_relation_cluster(cluster: RelationCluster) -> None:
    """Insert one relation cluster entry."""
    _facts_database().execute(
        """
        INSERT INTO relation_clusters (relation, cardinality, embedding, created_at)
        VALUES (:relation, :cardinality, :embedding, :created_at)
        """,
        {
            "relation": cluster.relation,
            "cardinality": cluster.cardinality,
            "embedding": cluster.embedding,
            "created_at": format_datetime(cluster.created_at),
        },
    )


def set_relation_cluster_embedding(relation: str, embedding: bytes) -> None:
    """Persist a computed embedding for an existing relation cluster."""
    _facts_database().execute(
        "UPDATE relation_clusters SET embedding = :embedding WHERE relation = :relation",
        {"relation": relation, "embedding": embedding},
    )


def list_relation_clusters() -> list[RelationCluster]:
    """List all relation cluster entries."""
    rows = (
        _facts_database()
        .execute("SELECT * FROM relation_clusters ORDER BY relation ASC")
        .fetchall()
    )
    return [_row_to_cluster(row) for row in rows]


# ── row mappers ───────────────────────────────────────────────────────────────


def _row_to_fact(row: dict[str, object]) -> Fact:
    from typing import cast

    return Fact(
        fact_id=str(row["fact_id"]),
        user_id=str(row["user_id"]),
        subject=str(row["subject"]),
        relation=str(row["relation"]),
        object=str(row["object"]),
        cardinality=cast(Cardinality, row["cardinality"]),
        status=cast(FactStatus, row["status"]),
        access_count=int(cast(int, row["access_count"])),
        first_accessed_at=parse_optional_datetime(row["first_accessed_at"]),
        last_accessed_at=parse_optional_datetime(row["last_accessed_at"]),
        expires_at=parse_optional_datetime(row["expires_at"]),
        valid_until=parse_optional_datetime(row["valid_until"]),
        created_at=parse_datetime(row["created_at"]),
        updated_at=parse_datetime(row["updated_at"]),
        source_turn=str(row["source_turn"]) if row["source_turn"] is not None else None,
        statement=str(row["statement"]) if row.get("statement") is not None else None,
    )


def _row_to_edge(row: dict[str, object]) -> FactEdge:
    return FactEdge(
        edge_id=str(row["edge_id"]),
        from_fact_id=str(row["from_fact_id"]),
        to_fact_id=str(row["to_fact_id"]),
        edge_type=str(row["edge_type"]),
        created_at=parse_datetime(row["created_at"]),
    )


def _row_to_cluster(row: dict[str, object]) -> RelationCluster:
    from typing import cast

    embedding = row["embedding"]
    return RelationCluster(
        relation=str(row["relation"]),
        cardinality=cast(Cardinality, row["cardinality"]),
        embedding=embedding if isinstance(embedding, bytes) else None,
        created_at=parse_datetime(row["created_at"]),
    )


def _fact_params(fact: Fact) -> dict[str, object | None]:
    return {
        "fact_id": fact.fact_id,
        "user_id": fact.user_id,
        "subject": fact.subject,
        "relation": fact.relation,
        "object": fact.object,
        "cardinality": fact.cardinality,
        "status": fact.status,
        "access_count": fact.access_count,
        "first_accessed_at": format_datetime(fact.first_accessed_at),
        "last_accessed_at": format_datetime(fact.last_accessed_at),
        "expires_at": format_datetime(fact.expires_at),
        "valid_until": format_datetime(fact.valid_until),
        "created_at": format_datetime(fact.created_at),
        "updated_at": format_datetime(fact.updated_at),
        "source_turn": fact.source_turn,
        "statement": fact.statement,
    }


def _now_iso() -> str:
    from datetime import UTC

    return datetime.now(UTC).replace(microsecond=0).isoformat()
