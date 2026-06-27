import json
import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration.test_migrations import apply_migrations


def _prepare_db(db_path) -> None:
    apply_migrations(db_path)
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)


@pytest.fixture(autouse=True)
def _reflection_state_db(tmp_path, monkeypatch):
    """Inject a default migrated reflection state DB for every test.

    reflection no longer falls back to DATABASE_URL (agent-runtime-db-routing-cleanup); tests
    that read back from a specific db_path override this via _use_db().
    """
    from fleetent import reflection
    from fleetent.memory import proposal_store as memory_proposal_store
    from fleetent.observability import traces

    db_path = tmp_path / "_reflection_autostate.db"
    _prepare_db(db_path)
    db = SQLiteDatabase(path=db_path)
    monkeypatch.setattr(reflection, "_state_db", db)
    monkeypatch.setattr(traces, "_state_db", db)
    monkeypatch.setattr(memory_proposal_store, "_db", db)


def _use_db(monkeypatch, db_path) -> None:
    """Point env + reflection state at an Alembic-migrated db.

    reflection no longer falls back to DATABASE_URL (agent-runtime-db-routing-cleanup), so
    its per-agent state DB is injected explicitly; DATABASE_URL stays set for traces/memory.
    """
    from fleetent import reflection
    from fleetent.memory import proposal_store as memory_proposal_store
    from fleetent.observability import traces

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(reflection, "_state_db", db)
    monkeypatch.setattr(traces, "_state_db", db)
    monkeypatch.setattr(memory_proposal_store, "_db", db)


async def test_reflection_public_api_is_importable():
    from fleetent.reflection import (
        ReflectionFinding,
        ReflectionReport,
        run_reflection,
    )

    assert ReflectionFinding
    assert ReflectionReport
    assert callable(run_reflection)


async def test_run_reflection_returns_report_with_required_fields(monkeypatch):
    from fleetent import observability, reflection

    monkeypatch.setattr(observability, "query_trace_events", lambda query: [])

    report = await reflection.run_reflection("user-1")

    assert report.id
    assert report.scope == "user-1"
    assert len(report.time_window) == 2
    assert all(isinstance(value, datetime) for value in report.time_window)
    assert report.findings == []
    assert isinstance(report.created_at, datetime)


async def test_run_reflection_queries_observability_public_api(monkeypatch):
    from fleetent import observability, reflection

    queries = []

    def fake_query_trace_events(query):
        queries.append(query)
        return []

    monkeypatch.setattr(observability, "query_trace_events", fake_query_trace_events)

    report = await reflection.run_reflection("user-1")

    assert report.findings == []
    assert len(queries) >= 1
    query = queries[0]
    assert query.user_id == "user-1"
    assert query.start_ts is not None
    assert query.end_ts is not None
    assert query.start_ts < query.end_ts


async def test_run_reflection_returns_empty_report_when_no_traces(monkeypatch):
    from fleetent import observability, reflection

    monkeypatch.setattr(observability, "query_trace_events", lambda query: [])

    report = await reflection.run_reflection("user-1")

    assert report.scope == "user-1"
    assert report.findings == []


async def test_run_reflection_reads_memory_layer_signals(monkeypatch):
    from fleetent import observability, reflection

    event = observability.TraceEvent(
        id="trace-1",
        run_id="run-1",
        event_type="agent_run_completed",
        payload={"user_input": "I prefer Python for backend services"},
        user_id="user-1",
    )
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(observability, "query_trace_events", lambda query: [event])
    monkeypatch.setattr(reflection.memory, "search_facts", search)

    await reflection.run_reflection("user-1")

    search.assert_awaited_once()
    assert search.await_args.args[0] == "user-1"
    assert "Python" in search.await_args.args[1]


async def test_repeated_user_fact_generates_memory_candidate(monkeypatch):
    from fleetent import observability, reflection

    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        ),
    ]
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search_facts", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")

    [finding] = [item for item in report.findings if item.type == "memory_candidate"]
    assert (
        finding.summary
        == "Repeated user fact may belong in memory: User prefers Python for backend work"
    )
    assert finding.evidence_ids == ["trace-1", "trace-2"]
    assert finding.metadata["fact"] == "User prefers Python for backend work"


async def test_conflicting_memory_signals_generate_memory_conflict(monkeypatch):
    from fleetent import observability, reflection
    from fleetent.memory.facts_models import Fact, SearchResult

    now = datetime.now(UTC)
    memories = [
        SearchResult(
            fact=Fact(
                fact_id="mem-1",
                user_id="user-1",
                subject="user",
                relation="located_in",
                object="Shanghai",
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
            ),
            score=0.9,
        ),
        SearchResult(
            fact=Fact(
                fact_id="mem-2",
                user_id="user-1",
                subject="user",
                relation="located_in",
                object="Beijing",
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
            ),
            score=0.8,
        ),
    ]
    monkeypatch.setattr(
        observability,
        "query_trace_events",
        lambda query: [
            observability.TraceEvent(
                id="trace-1",
                run_id="run-1",
                event_type="agent_run_completed",
                payload={"user_input": "Please remember my profile"},
                user_id="user-1",
            )
        ],
    )
    monkeypatch.setattr(reflection.memory, "search_facts", AsyncMock(return_value=memories))

    report = await reflection.run_reflection("user-1")

    [finding] = [item for item in report.findings if item.type == "memory_conflict"]
    assert finding.evidence_ids == ["mem-1", "mem-2"]
    assert finding.metadata["field"] == "located_in"
    assert finding.metadata["subject"] == "user"


async def test_repeated_task_pattern_generates_skill_opportunity(monkeypatch):
    from fleetent import observability, reflection

    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"task_pattern": "summarize weekly Jira progress"},
            agent_name="agent-1",
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"task_pattern": "summarize weekly Jira progress"},
            agent_name="agent-1",
            user_id="user-1",
        ),
    ]
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search_facts", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")

    [finding] = [item for item in report.findings if item.type == "skill_opportunity"]
    assert (
        finding.summary
        == "Repeated task pattern may become a skill: summarize weekly Jira progress"
    )
    assert finding.evidence_ids == ["trace-1", "trace-2"]
    assert finding.metadata["pattern"] == "summarize weekly Jira progress"


async def test_run_reflection_persists_report_without_raw_transcript(tmp_path, monkeypatch):
    from fleetent import observability, reflection

    db_path = tmp_path / "reflection.db"
    _prepare_db(db_path)
    raw_user_input = "My private transcript says I prefer Python"
    raw_agent_reply = "Agent reply should not be stored verbatim"
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={
                "user_input": raw_user_input,
                "agent_reply": raw_agent_reply,
                "memory_fact": "User prefers Python",
            },
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={
                "user_input": raw_user_input,
                "agent_reply": raw_agent_reply,
                "memory_fact": "User prefers Python",
            },
            user_id="user-1",
        ),
    ]
    _use_db(monkeypatch, db_path)
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search_facts", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT domain, scope, time_window_start, time_window_end, findings_json, created_at
            FROM reflection_reports
            WHERE id = ?
            """,
            (report.id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "memory"
    assert row[1] == "user-1"
    assert datetime.fromisoformat(row[2]) == report.time_window[0]
    assert datetime.fromisoformat(row[3]) == report.time_window[1]
    assert datetime.fromisoformat(row[5]) == report.created_at

    findings_payload = json.loads(row[4])
    assert findings_payload == [
        {
            "type": "memory_candidate",
            "summary": "Repeated user fact may belong in memory: User prefers Python",
            "evidence_ids": ["trace-1", "trace-2"],
            "metadata": {"fact": "User prefers Python", "count": "2"},
        }
    ]
    persisted = row[4]
    assert raw_user_input not in persisted
    assert raw_agent_reply not in persisted


async def test_run_reflection_persists_generated_proposals_with_report_id(tmp_path, monkeypatch):
    from fleetent import observability, reflection

    db_path = tmp_path / "reflection.db"
    _prepare_db(db_path)
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={
                "memory_fact": "User prefers Python",
                "task_pattern": "summarize weekly Jira progress",
            },
            user_id="user-1",
            agent_name="agent-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={
                "memory_fact": "User prefers Python",
                "task_pattern": "summarize weekly Jira progress",
            },
            user_id="user-1",
            agent_name="agent-1",
        ),
    ]
    _use_db(monkeypatch, db_path)
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search_facts", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT domain, report_id
            FROM reflection_proposals
            ORDER BY domain ASC
            """
        ).fetchall()

    assert rows == [("memory", report.id), ("skill", report.id)]


async def test_run_reflection_persists_report_proposal_provenance_links(tmp_path, monkeypatch):
    from fleetent import observability, reflection

    db_path = tmp_path / "reflection.db"
    _prepare_db(db_path)
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={
                "memory_fact": "User prefers Python",
                "task_pattern": "prepare release notes",
            },
            user_id="user-1",
            agent_name="agent-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={
                "memory_fact": "User prefers Python",
                "task_pattern": "prepare release notes",
            },
            user_id="user-1",
            agent_name="agent-1",
        ),
    ]
    _use_db(monkeypatch, db_path)
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search_facts", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")

    with sqlite3.connect(db_path) as conn:
        proposal_ids = [
            row[0]
            for row in conn.execute(
                """
                SELECT id
                FROM reflection_proposals
                WHERE report_id = ?
                ORDER BY domain ASC, id ASC
                """,
                (report.id,),
            ).fetchall()
        ]
        linked_report_ids = [
            row[0]
            for row in conn.execute(
                """
                SELECT reports.id
                FROM reflection_reports AS reports
                JOIN reflection_proposals AS proposals
                  ON proposals.report_id = reports.id
                WHERE proposals.id IN (
                    SELECT id FROM reflection_proposals ORDER BY domain ASC, id ASC
                )
                ORDER BY proposals.domain ASC, proposals.id ASC
                """
            ).fetchall()
        ]

    assert len(proposal_ids) == 2
    assert linked_report_ids == [report.id, report.id]


async def test_reportless_proposal_persists_null_report_id_and_remains_usable(
    tmp_path, monkeypatch
):
    from fleetent import reflection

    db_path = tmp_path / "reflection.db"
    _prepare_db(db_path)
    _use_db(monkeypatch, db_path)

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-1"],
        proposed_content="User prefers Python.",
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-1"],
    )

    with sqlite3.connect(db_path) as conn:
        persisted = conn.execute(
            "SELECT report_id FROM reflection_proposals WHERE id = ?",
            (proposal.id,),
        ).fetchone()

    loaded = reflection.get_memory_maintenance_proposal(proposal.id)
    listed = reflection.list_memory_maintenance_proposals("user-1")
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="user-1")
    applied = await reflection.apply_memory_maintenance_proposal(
        proposal.id,
        actor_user_id="user-1",
    )

    assert persisted == (None,)
    assert loaded.report_id is None
    assert listed[0].report_id is None
    assert applied.report_id is None


async def test_skill_opportunity_does_not_modify_skills_directory(tmp_path, monkeypatch):
    from fleetent import observability, reflection

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    existing_skill = skills_dir / "existing.md"
    existing_skill.write_text("existing skill", encoding="utf-8")
    before = {
        path.relative_to(skills_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in skills_dir.rglob("*")
        if path.is_file()
    }
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"task_pattern": "summarize weekly Jira progress"},
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"task_pattern": "summarize weekly Jira progress"},
            user_id="user-1",
        ),
    ]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search_facts", AsyncMock(return_value=[]))

    await reflection.run_reflection("user-1")

    after = {
        path.relative_to(skills_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in skills_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
