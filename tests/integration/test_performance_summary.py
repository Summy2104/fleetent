from datetime import UTC, datetime, timedelta

from fleetent.observability import (
    ModelPerformance,
    PerformanceQuery,
    PerformanceSummary,
    PermissionSummary,
    ToolPerformance,
    TraceEvent,
    get_performance_summary,
    performance,
)


def test_performance_summary_public_api_is_importable():
    query = PerformanceQuery(user_id="user-1")
    summary = PerformanceSummary(
        run_count=0,
        completed_count=0,
        failed_count=0,
        failure_rate=0,
        avg_elapsed_s=0,
        p50_elapsed_s=0,
        p95_elapsed_s=0,
        llm_call_count=0,
        llm_error_count=0,
        avg_llm_elapsed_s=0,
        p95_llm_elapsed_s=0,
        fallback_count=0,
        fallback_rate=0,
        tool_call_count=0,
        tool_error_count=0,
        avg_tool_elapsed_s=0,
        p95_tool_elapsed_s=0,
        permission_requested_count=0,
        permission_approved_count=0,
        permission_rejected_count=0,
        permission_timeout_count=0,
        avg_permission_wait_s=0,
        by_model=[],
        by_tool=[],
        permission=PermissionSummary(
            requested_count=0,
            approved_count=0,
            rejected_count=0,
            timeout_count=0,
            avg_wait_s=0,
        ),
    )
    model = ModelPerformance(model="gpt-test", call_count=0, error_count=0, avg_elapsed_s=0)
    tool = ToolPerformance(tool_name="search", call_count=0, error_count=0, avg_elapsed_s=0)

    assert query.user_id == "user-1"
    assert summary.by_model == []
    assert model.model == "gpt-test"
    assert tool.tool_name == "search"
    assert callable(get_performance_summary)


def test_performance_summary_returns_zero_values_when_no_trace_events(monkeypatch):
    monkeypatch.setattr(performance, "query_trace_events", lambda query: [])

    summary = get_performance_summary(PerformanceQuery())

    assert summary == PerformanceSummary(
        run_count=0,
        completed_count=0,
        failed_count=0,
        failure_rate=0,
        avg_elapsed_s=0,
        p50_elapsed_s=0,
        p95_elapsed_s=0,
        llm_call_count=0,
        llm_error_count=0,
        avg_llm_elapsed_s=0,
        p95_llm_elapsed_s=0,
        fallback_count=0,
        fallback_rate=0,
        tool_call_count=0,
        tool_error_count=0,
        avg_tool_elapsed_s=0,
        p95_tool_elapsed_s=0,
        permission_requested_count=0,
        permission_approved_count=0,
        permission_rejected_count=0,
        permission_timeout_count=0,
        avg_permission_wait_s=0,
        by_model=[],
        by_tool=[],
        permission=PermissionSummary(
            requested_count=0,
            approved_count=0,
            rejected_count=0,
            timeout_count=0,
            avg_wait_s=0,
        ),
    )


def test_performance_summary_aggregates_terminal_run_counts_and_latency(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"elapsed_s": 1},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="agent_run_failed",
            payload={"elapsed_s": 2},
        ),
        TraceEvent(
            run_id="run-3",
            event_type="agent_run_completed",
            payload={"elapsed_s": 3},
        ),
        TraceEvent(
            run_id="run-4",
            event_type="agent_run_failed",
            payload={"elapsed_s": 4},
        ),
        TraceEvent(
            run_id="run-5",
            event_type="agent_run_completed",
            payload={"elapsed_s": 5},
        ),
        TraceEvent(
            run_id="run-started",
            event_type="agent_run_started",
            payload={"elapsed_s": 100},
        ),
    ]
    monkeypatch.setattr(performance, "query_trace_events", lambda query: events)

    summary = get_performance_summary(PerformanceQuery())

    assert summary.run_count == 5
    assert summary.completed_count == 3
    assert summary.failed_count == 2
    assert summary.failure_rate == 0.4
    assert summary.avg_elapsed_s == 3.0
    assert summary.p50_elapsed_s == 3.0
    assert summary.p95_elapsed_s == 5.0


def test_performance_summary_aggregates_llm_fallback_and_model_groups(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"elapsed_s": 10},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="agent_run_failed",
            payload={"elapsed_s": 20},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="llm_call_completed",
            payload={"model": "model-a", "elapsed_s": 1},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="llm_call_failed",
            payload={"model": "model-a", "elapsed_s": 2},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="llm_call_completed",
            payload={"model": "model-b", "elapsed_s": 3},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="model_fallback_triggered",
            payload={"from_model": "model-a", "to_model": "model-b"},
        ),
    ]
    monkeypatch.setattr(performance, "query_trace_events", lambda query: events)

    summary = get_performance_summary(PerformanceQuery())

    assert summary.llm_call_count == 3
    assert summary.llm_error_count == 1
    assert summary.avg_llm_elapsed_s == 2.0
    assert summary.p95_llm_elapsed_s == 3.0
    assert summary.fallback_count == 1
    assert summary.fallback_rate == 0.5
    assert summary.by_model == [
        ModelPerformance(model="model-a", call_count=2, error_count=1, avg_elapsed_s=1.5),
        ModelPerformance(model="model-b", call_count=1, error_count=0, avg_elapsed_s=3.0),
    ]


def test_performance_summary_aggregates_tool_and_permission_metrics(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="tool_call_completed",
            payload={"tool_name": "search", "elapsed_s": 1},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="tool_call_failed",
            payload={"tool_name": "search", "elapsed_s": 5},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="tool_call_completed",
            payload={"tool_name": "calc", "elapsed_s": 3},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="permission_requested",
            payload={"approval_id": "approval-1"},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="permission_requested",
            payload={"approval_id": "approval-2"},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="permission_resolved",
            payload={"approval_id": "approval-1", "decision": "approved", "elapsed_s": 4},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="permission_resolved",
            payload={"approval_id": "approval-2", "decision": "rejected", "elapsed_s": 6},
        ),
        TraceEvent(
            run_id="run-1",
            event_type="permission_resolved",
            payload={"approval_id": "approval-3", "decision": "timeout", "elapsed_s": 8},
        ),
    ]
    monkeypatch.setattr(performance, "query_trace_events", lambda query: events)

    summary = get_performance_summary(PerformanceQuery())

    assert summary.tool_call_count == 3
    assert summary.tool_error_count == 1
    assert summary.avg_tool_elapsed_s == 3.0
    assert summary.p95_tool_elapsed_s == 5.0
    assert summary.by_tool == [
        ToolPerformance(tool_name="search", call_count=2, error_count=1, avg_elapsed_s=3.0),
        ToolPerformance(tool_name="calc", call_count=1, error_count=0, avg_elapsed_s=3.0),
    ]
    assert summary.permission_requested_count == 2
    assert summary.permission_approved_count == 1
    assert summary.permission_rejected_count == 1
    assert summary.permission_timeout_count == 1
    assert summary.avg_permission_wait_s == 6.0
    assert summary.permission == PermissionSummary(
        requested_count=2,
        approved_count=1,
        rejected_count=1,
        timeout_count=1,
        avg_wait_s=6.0,
    )


def test_performance_summary_maps_supported_filters_to_trace_query(monkeypatch):
    captured = {}
    start_ts = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    end_ts = start_ts + timedelta(hours=1)

    def fake_query_trace_events(query):
        captured["query"] = query
        return []

    monkeypatch.setattr(performance, "query_trace_events", fake_query_trace_events)

    get_performance_summary(
        PerformanceQuery(
            user_id="user-1",
            agent_name="agent-1",
            tenant_id="tenant-1",
            session_id="session-1",
            start_ts=start_ts,
            end_ts=end_ts,
            limit=123,
        )
    )

    trace_query = captured["query"]
    assert trace_query.user_id == "user-1"
    assert trace_query.agent_name == "agent-1"
    assert trace_query.session_id == "session-1"
    assert trace_query.tenant_id == "tenant-1"
    assert trace_query.event_type is None
    assert trace_query.start_ts == start_ts
    assert trace_query.end_ts == end_ts
    assert trace_query.limit == 123


def test_performance_summary_filters_session_id_after_trace_query(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"elapsed_s": 1},
            session_id="session-1",
        ),
        TraceEvent(
            run_id="run-2",
            event_type="agent_run_failed",
            payload={"elapsed_s": 2},
            session_id="session-2",
        ),
        TraceEvent(
            run_id="run-3",
            event_type="llm_call_completed",
            payload={"model": "model-a", "elapsed_s": 3},
            session_id="session-1",
        ),
    ]
    monkeypatch.setattr(performance, "query_trace_events", lambda query: events)

    summary = get_performance_summary(PerformanceQuery(session_id="session-1"))

    assert summary.run_count == 1
    assert summary.completed_count == 1
    assert summary.failed_count == 0
    assert summary.llm_call_count == 1
    assert summary.avg_llm_elapsed_s == 3.0


def test_performance_summary_tolerates_missing_invalid_and_unknown_payload_fields(monkeypatch):
    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="agent_run_failed",
            payload={"elapsed_s": "nan"},
        ),
        TraceEvent(
            run_id="run-3",
            event_type="agent_run_completed",
            payload={"elapsed_s": "2.5"},
        ),
        TraceEvent(
            run_id="run-4",
            event_type="llm_call_completed",
            payload={"elapsed_s": "bad"},
        ),
        TraceEvent(
            run_id="run-5",
            event_type="tool_call_completed",
            payload={"elapsed_s": ""},
        ),
        TraceEvent(
            run_id="run-6",
            event_type="permission_resolved",
            payload={"decision": "approved", "elapsed_s": None},
        ),
    ]
    monkeypatch.setattr(performance, "query_trace_events", lambda query: events)

    summary = get_performance_summary(PerformanceQuery())

    assert summary.run_count == 3
    assert summary.completed_count == 2
    assert summary.failed_count == 1
    assert summary.avg_elapsed_s == 2.5
    assert summary.p50_elapsed_s == 2.5
    assert summary.p95_elapsed_s == 2.5
    assert summary.llm_call_count == 1
    assert summary.avg_llm_elapsed_s == 0
    assert summary.by_model == [
        ModelPerformance(model="unknown", call_count=1, error_count=0, avg_elapsed_s=0)
    ]
    assert summary.tool_call_count == 1
    assert summary.avg_tool_elapsed_s == 0
    assert summary.by_tool == [
        ToolPerformance(tool_name="unknown", call_count=1, error_count=0, avg_elapsed_s=0)
    ]
    assert summary.permission_approved_count == 1
    assert summary.avg_permission_wait_s == 0
