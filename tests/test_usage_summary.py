from datetime import UTC, datetime, timedelta

from fleetent.observability import (
    ModelUsage,
    TraceEvent,
    UsageQuery,
    UsageSummary,
    get_usage_summary,
    usage,
)


def test_usage_summary_public_api_is_importable():
    query = UsageQuery(user_id="user-1")
    summary = UsageSummary(
        run_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        total_elapsed_s=0,
        avg_elapsed_s=0,
        by_model=[],
    )
    model_usage = ModelUsage(
        model="gpt-test",
        run_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        total_elapsed_s=0,
        avg_elapsed_s=0,
    )

    assert query.user_id == "user-1"
    assert summary.by_model == []
    assert model_usage.model == "gpt-test"
    assert callable(get_usage_summary)


def test_usage_summary_returns_zero_values_when_no_completed_runs(monkeypatch):
    monkeypatch.setattr(usage, "query_trace_events", lambda query: [])

    summary = get_usage_summary(UsageQuery())

    assert summary == UsageSummary(
        run_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        total_elapsed_s=0,
        avg_elapsed_s=0,
        by_model=[],
    )


def test_usage_summary_aggregates_completed_run_tokens_and_elapsed(monkeypatch):
    base_ts = datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    events = [
        TraceEvent(
            id="event-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": 10, "completion": 5, "total": 15},
                "elapsed_s": 1.5,
                "model_used": "model-a",
            },
            ts=base_ts,
        ),
        TraceEvent(
            id="event-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": 3, "completion": 7, "total": 10},
                "elapsed_s": 2.5,
                "model_used": "model-b",
            },
            ts=base_ts + timedelta(minutes=1),
        ),
    ]
    monkeypatch.setattr(usage, "query_trace_events", lambda query: events)

    summary = get_usage_summary(UsageQuery())

    assert summary.run_count == 2
    assert summary.prompt_tokens == 13
    assert summary.completion_tokens == 12
    assert summary.total_tokens == 25
    assert summary.total_elapsed_s == 4.0
    assert summary.avg_elapsed_s == 2.0


def test_usage_summary_maps_query_filters_to_trace_query(monkeypatch):
    captured = {}
    start_ts = datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
    end_ts = start_ts + timedelta(hours=1)

    def fake_query_trace_events(query):
        captured["query"] = query
        return []

    monkeypatch.setattr(usage, "query_trace_events", fake_query_trace_events)

    get_usage_summary(
        UsageQuery(
            user_id="user-1",
            agent_id="agent-1",
            tenant_id="tenant-1",
            session_id="session-1",
            start_ts=start_ts,
            end_ts=end_ts,
            limit=123,
        )
    )

    trace_query = captured["query"]
    assert trace_query.user_id == "user-1"
    assert trace_query.agent_id == "agent-1"
    assert trace_query.tenant_id == "tenant-1"
    assert trace_query.event_type == "agent_run_completed"
    assert trace_query.start_ts == start_ts
    assert trace_query.end_ts == end_ts
    assert trace_query.limit == 123


def test_usage_summary_filters_session_id_in_memory(monkeypatch):
    events = [
        TraceEvent(
            id="event-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"tokens": {"prompt": 5, "completion": 4, "total": 9}, "elapsed_s": 1},
            session_id="session-1",
        ),
        TraceEvent(
            id="event-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"tokens": {"prompt": 7, "completion": 6, "total": 13}, "elapsed_s": 2},
            session_id="session-2",
        ),
    ]
    monkeypatch.setattr(usage, "query_trace_events", lambda query: events)

    summary = get_usage_summary(UsageQuery(session_id="session-1"))

    assert summary.run_count == 1
    assert summary.prompt_tokens == 5
    assert summary.completion_tokens == 4
    assert summary.total_tokens == 9
    assert summary.total_elapsed_s == 1


def test_usage_summary_groups_by_model_and_sorts_stably(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": 10, "completion": 5, "total": 15},
                "elapsed_s": 1.0,
                "model_used": "model-b",
            },
        ),
        TraceEvent(
            run_id="run-2",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": 20, "completion": 10, "total": 30},
                "elapsed_s": 2.0,
                "model_used": "model-a",
            },
        ),
        TraceEvent(
            run_id="run-3",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": 3, "completion": 12, "total": 15},
                "elapsed_s": 3.0,
                "model_used": "model-b",
            },
        ),
        TraceEvent(
            run_id="run-4",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": 12, "completion": 18, "total": 30},
                "elapsed_s": 4.0,
                "model_used": "model-c",
            },
        ),
    ]
    monkeypatch.setattr(usage, "query_trace_events", lambda query: events)

    summary = get_usage_summary(UsageQuery())

    assert summary.by_model == [
        ModelUsage(
            model="model-a",
            run_count=1,
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
            total_elapsed_s=2.0,
            avg_elapsed_s=2.0,
        ),
        ModelUsage(
            model="model-b",
            run_count=2,
            prompt_tokens=13,
            completion_tokens=17,
            total_tokens=30,
            total_elapsed_s=4.0,
            avg_elapsed_s=2.0,
        ),
        ModelUsage(
            model="model-c",
            run_count=1,
            prompt_tokens=12,
            completion_tokens=18,
            total_tokens=30,
            total_elapsed_s=4.0,
            avg_elapsed_s=4.0,
        ),
    ]


def test_usage_summary_tolerates_missing_and_invalid_payload_fields(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": "bad", "completion": None, "total": "oops"},
                "elapsed_s": "bad",
                "model_used": None,
            },
        ),
        TraceEvent(
            run_id="run-3",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": "4", "completion": "6"},
                "elapsed_s": "2.5",
                "model_used": "model-a",
            },
        ),
    ]
    monkeypatch.setattr(usage, "query_trace_events", lambda query: events)

    summary = get_usage_summary(UsageQuery())

    assert summary.run_count == 3
    assert summary.prompt_tokens == 4
    assert summary.completion_tokens == 6
    assert summary.total_tokens == 10
    assert summary.total_elapsed_s == 2.5
    assert summary.by_model == [
        ModelUsage(
            model="model-a",
            run_count=1,
            prompt_tokens=4,
            completion_tokens=6,
            total_tokens=10,
            total_elapsed_s=2.5,
            avg_elapsed_s=2.5,
        ),
        ModelUsage(
            model="unknown",
            run_count=2,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            total_elapsed_s=0,
            avg_elapsed_s=0,
        ),
    ]


def test_usage_summary_ignores_non_completed_events(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"tokens": {"prompt": 1, "completion": 2, "total": 3}, "elapsed_s": 1},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="tool_call_completed",
            payload={"tokens": {"prompt": 10, "completion": 20, "total": 30}, "elapsed_s": 10},
        ),
    ]
    monkeypatch.setattr(usage, "query_trace_events", lambda query: events)

    summary = get_usage_summary(UsageQuery())

    assert summary.run_count == 1
    assert summary.prompt_tokens == 1
    assert summary.completion_tokens == 2
    assert summary.total_tokens == 3
    assert summary.total_elapsed_s == 1
