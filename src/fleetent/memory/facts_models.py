"""Dataclasses and type aliases for the user memory facts system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

FactStatus = Literal["active", "superseded", "archived", "retracted"]
Cardinality = Literal["single", "multi"]
FactScope = Literal["situational", "always"]
ClassifyVerdict = Literal["Equivalent", "Contradict", "NewSubsumed", "Subsumes", "Orthogonal"]

# Pseudo-relation the LLM emits for "X 改叫 Y" — not a real relation: it is a
# subject-rename directive, handled by migrating the old subject's facts at commit
# time and never stored as a fact itself.
RENAME_RELATION = "renamed_to"

# Pseudo-relation for "忘记 / 删掉 X" — a forget directive: retracts the matching
# fact(s) at commit time (a specific object, or the whole subject when object
# names the subject itself) and is never stored as a fact.
FORGET_RELATION = "forget"


@dataclass(frozen=True)
class Fact:
    """A single user memory fact stored as a (subject, relation, object) triple."""

    fact_id: str
    user_id: str
    subject: str
    relation: str
    object: str
    cardinality: Cardinality
    status: FactStatus
    access_count: int
    first_accessed_at: datetime | None
    last_accessed_at: datetime | None
    expires_at: datetime | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime
    source_turn: str | None
    statement: str | None = None
    scope: FactScope = "situational"


@dataclass(frozen=True)
class FactEdge:
    """A directed supersedes relationship between two facts."""

    edge_id: str
    from_fact_id: str
    to_fact_id: str
    edge_type: str
    created_at: datetime


@dataclass(frozen=True)
class RelationCluster:
    """A canonical relation name with its cardinality and optional embedding."""

    relation: str
    cardinality: Cardinality
    embedding: bytes | None
    created_at: datetime


@dataclass(frozen=True)
class RawFact:
    """A fact as extracted by the LLM before relation resolution.

    ``statement`` is the LLM's natural-language rendering of the triple, with an
    explicit subject ("用户的名字是 Xin"), used verbatim at injection time.
    """

    subject: str
    relation: str
    object: str
    # Temporal-intent enum from the LLM (today / this_week / none …); the concrete
    # expiry date is computed in code (facts_temporal), never by the model.
    temporal: str = "none"
    statement: str | None = None
    scope: FactScope = "situational"


@dataclass(frozen=True)
class ResolvedFact:
    """A fact after relation has been normalized to a relation_clusters entry."""

    subject: str
    relation: str
    object: str
    temporal: str = "none"
    cardinality: Cardinality = "multi"
    statement: str | None = None
    scope: FactScope = "situational"


@dataclass(frozen=True)
class ClassifiedFact:
    """A fact after classify_relation has assigned a verdict."""

    subject: str
    relation: str
    object: str
    temporal: str = "none"
    cardinality: Cardinality = "multi"
    verdict: ClassifyVerdict = "Orthogonal"
    statement: str | None = None
    scope: FactScope = "situational"


@dataclass(frozen=True)
class SearchResult:
    """A fact retrieved via semantic search with its similarity score."""

    fact: Fact
    score: float
