import json
import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from tests.integration.test_migrations import apply_migrations


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
    [query] = queries
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
    monkeypatch.setattr(reflection.memory, "search", search)

    await reflection.run_reflection("user-1")

    search.assert_awaited_once()
    assert search.await_args.args[0] == "user-1"
    assert "Python" in search.await_args.args[1]


async def test_run_reflection_does_not_call_memory_write_api(monkeypatch):
    from fleetent import memory as memory_layer
    from fleetent import observability, reflection

    write_memory = AsyncMock()
    monkeypatch.setattr(observability, "query_trace_events", lambda query: [])
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(memory_layer, "extract_and_update", write_memory)

    await reflection.run_reflection("user-1")

    write_memory.assert_not_awaited()


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
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")

    [finding] = [item for item in report.findings if item.type == "memory_candidate"]
    assert (
        finding.summary
        == "Repeated user fact may belong in memory: User prefers Python for backend work"
    )
    assert finding.evidence_ids == ["trace-1", "trace-2"]
    assert finding.metadata["fact"] == "User prefers Python for backend work"


async def test_conflicting_memory_signals_generate_memory_conflict(monkeypatch):
    from fleetent import memory as memory_layer
    from fleetent import observability, reflection

    now = datetime.now(UTC)
    memories = [
        memory_layer.MemoryItem(
            id="mem-1",
            user_id="user-1",
            type="identity",
            content="User location is Shanghai",
            created_at=now,
            updated_at=now,
            expires_at=None,
        ),
        memory_layer.MemoryItem(
            id="mem-2",
            user_id="user-1",
            type="identity",
            content="User location is Beijing",
            created_at=now,
            updated_at=now,
            expires_at=None,
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
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=memories))

    report = await reflection.run_reflection("user-1")

    [finding] = [item for item in report.findings if item.type == "memory_conflict"]
    assert finding.evidence_ids == ["mem-1", "mem-2"]
    assert finding.metadata["field"] == "location"


async def test_repeated_task_pattern_generates_skill_opportunity(monkeypatch):
    from fleetent import observability, reflection

    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"task_pattern": "summarize weekly Jira progress"},
            agent_id="agent-1",
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"task_pattern": "summarize weekly Jira progress"},
            agent_id="agent-1",
            user_id="user-1",
        ),
    ]
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))

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
    apply_migrations(db_path)
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
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT scope, time_window_start, time_window_end, findings_json, created_at
            FROM reflection_reports
            WHERE id = ?
            """,
            (report.id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "user-1"
    assert datetime.fromisoformat(row[1]) == report.time_window[0]
    assert datetime.fromisoformat(row[2]) == report.time_window[1]
    assert datetime.fromisoformat(row[4]) == report.created_at

    findings_payload = json.loads(row[3])
    assert findings_payload == [
        {
            "type": "memory_candidate",
            "summary": "Repeated user fact may belong in memory: User prefers Python",
            "evidence_ids": ["trace-1", "trace-2"],
            "metadata": {"fact": "User prefers Python", "count": "2"},
        }
    ]
    persisted = row[3]
    assert raw_user_input not in persisted
    assert raw_agent_reply not in persisted


async def test_memory_findings_do_not_modify_memory_items_table(tmp_path, monkeypatch):
    from fleetent import memory as memory_layer
    from fleetent import observability, reflection

    db_path = tmp_path / "reflection.db"
    apply_migrations(db_path)
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mem-1",
                "user-1",
                "identity",
                "User location is Shanghai",
                now,
                now,
                None,
            ),
        )
        before = conn.execute("SELECT id, content FROM memory_items ORDER BY id").fetchall()

    memories = [
        memory_layer.MemoryItem(
            id="mem-1",
            user_id="user-1",
            type="identity",
            content="User location is Shanghai",
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
            expires_at=None,
        ),
        memory_layer.MemoryItem(
            id="mem-2",
            user_id="user-1",
            type="identity",
            content="User location is Beijing",
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
            expires_at=None,
        ),
    ]
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python"},
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python"},
            user_id="user-1",
        ),
    ]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=memories))

    await reflection.run_reflection("user-1")

    with sqlite3.connect(db_path) as conn:
        after = conn.execute("SELECT id, content FROM memory_items ORDER BY id").fetchall()
    assert after == before


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
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))

    await reflection.run_reflection("user-1")

    after = {
        path.relative_to(skills_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in skills_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
