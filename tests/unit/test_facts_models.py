"""Unit tests: facts_models dataclasses and type literals."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


def test_fact_fields_complete() -> None:
    from fleetent.memory.facts_models import Fact

    now = datetime.now(UTC)
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
    assert fact.fact_id == "f1"
    assert fact.status == "active"
    assert fact.cardinality == "single"


def test_fact_edge_fields_complete() -> None:
    from fleetent.memory.facts_models import FactEdge

    now = datetime.now(UTC)
    edge = FactEdge(
        edge_id="e1",
        from_fact_id="f2",
        to_fact_id="f1",
        edge_type="supersedes",
        created_at=now,
    )
    assert edge.edge_type == "supersedes"


def test_relation_cluster_fields() -> None:
    from fleetent.memory.facts_models import RelationCluster

    now = datetime.now(UTC)
    rc = RelationCluster(
        relation="is_role",
        cardinality="single",
        embedding=None,
        created_at=now,
    )
    assert rc.cardinality == "single"


def test_raw_fact_fields() -> None:
    from fleetent.memory.facts_models import RawFact

    rf = RawFact(subject="user", relation="has_skill", object="Python", temporal="none")
    assert rf.object == "Python"
    assert rf.temporal == "none"


def test_resolved_fact_fields() -> None:
    from fleetent.memory.facts_models import ResolvedFact

    rf = ResolvedFact(
        subject="user",
        relation="has_skill",
        object="Python",
        temporal="none",
        cardinality="multi",
    )
    assert rf.cardinality == "multi"


def test_classified_fact_fields() -> None:
    from fleetent.memory.facts_models import ClassifiedFact

    cf = ClassifiedFact(
        subject="user",
        relation="is_role",
        object="Go developer",
        temporal="none",
        cardinality="single",
        verdict="Contradict",
    )
    assert cf.verdict == "Contradict"


def test_search_result_fields() -> None:
    from fleetent.memory.facts_models import Fact, SearchResult

    now = datetime.now(UTC)
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
    sr = SearchResult(fact=fact, score=0.87)
    assert sr.score == pytest.approx(0.87)


def test_fact_status_literal_values() -> None:
    from fleetent.memory.facts_models import FactStatus

    valid: list[FactStatus] = ["active", "superseded", "archived", "retracted"]
    assert len(valid) == 4


def test_cardinality_literal_values() -> None:
    from fleetent.memory.facts_models import Cardinality

    valid: list[Cardinality] = ["single", "multi"]
    assert len(valid) == 2


def test_classify_verdict_literal_values() -> None:
    from fleetent.memory.facts_models import ClassifyVerdict

    valid: list[ClassifyVerdict] = [
        "Equivalent",
        "Contradict",
        "NewSubsumed",
        "Subsumes",
        "Orthogonal",
    ]
    assert len(valid) == 5
