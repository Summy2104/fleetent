from math import isnan

from fleetent.observability import TraceEvent


def test_performance_summary_ignores_invalid_elapsed_and_uses_unknown_groups(monkeypatch):
    from fleetent.observability import PerformanceQuery, performance

    events = [
        TraceEvent(run_id="run-1", event_type="agent_run_completed", payload={"elapsed_s": 1}),
        TraceEvent(run_id="run-2", event_type="agent_run_failed", payload={"elapsed_s": -2}),
        TraceEvent(run_id="run-3", event_type="agent_run_completed", payload={"elapsed_s": "bad"}),
        TraceEvent(run_id="run-4", event_type="agent_run_failed", payload={"elapsed_s": "nan"}),
        TraceEvent(run_id="run-5", event_type="agent_run_completed", payload={"elapsed_s": "inf"}),
        TraceEvent(run_id="run-1", event_type="llm_call_completed", payload={"elapsed_s": 2}),
        TraceEvent(
            run_id="run-1", event_type="llm_call_failed", payload={"model": "", "elapsed_s": -3}
        ),
        TraceEvent(run_id="run-1", event_type="tool_call_completed", payload={"elapsed_s": 4}),
        TraceEvent(
            run_id="run-1",
            event_type="tool_call_failed",
            payload={"tool_name": None, "elapsed_s": float("nan")},
        ),
    ]
    monkeypatch.setattr(performance, "query_trace_events", lambda query: events)

    summary = performance.get_performance_summary(PerformanceQuery())

    assert summary.run_count == 5
    assert summary.avg_elapsed_s == 1
    assert summary.p50_elapsed_s == 1
    assert summary.p95_elapsed_s == 1
    assert summary.avg_llm_elapsed_s == 2
    assert summary.avg_tool_elapsed_s == 4
    assert summary.by_model[0].model == "unknown"
    assert summary.by_model[0].call_count == 2
    assert summary.by_tool[0].tool_name == "unknown"
    assert summary.by_tool[0].call_count == 2


def test_performance_summary_sorts_groups_by_count_then_name(monkeypatch):
    from fleetent.observability import (
        ModelPerformance,
        PerformanceQuery,
        ToolPerformance,
        performance,
    )

    events = [
        TraceEvent(run_id="run-1", event_type="llm_call_completed", payload={"model": "zeta"}),
        TraceEvent(run_id="run-1", event_type="llm_call_completed", payload={"model": "alpha"}),
        TraceEvent(run_id="run-1", event_type="llm_call_failed", payload={"model": "alpha"}),
        TraceEvent(
            run_id="run-1", event_type="tool_call_completed", payload={"tool_name": "ztool"}
        ),
        TraceEvent(
            run_id="run-1", event_type="tool_call_completed", payload={"tool_name": "atool"}
        ),
        TraceEvent(run_id="run-1", event_type="tool_call_failed", payload={"tool_name": "atool"}),
    ]
    monkeypatch.setattr(performance, "query_trace_events", lambda query: events)

    summary = performance.get_performance_summary(PerformanceQuery())

    assert summary.by_model == [
        ModelPerformance(model="alpha", call_count=2, error_count=1, avg_elapsed_s=0),
        ModelPerformance(model="zeta", call_count=1, error_count=0, avg_elapsed_s=0),
    ]
    assert summary.by_tool == [
        ToolPerformance(tool_name="atool", call_count=2, error_count=1, avg_elapsed_s=0),
        ToolPerformance(tool_name="ztool", call_count=1, error_count=0, avg_elapsed_s=0),
    ]


def test_usage_summary_tolerates_missing_tokens_invalid_elapsed_and_session_filter(monkeypatch):
    from fleetent.observability import UsageQuery, usage

    events = [
        TraceEvent(
            run_id="run-1",
            session_id="session-1",
            event_type="agent_run_completed",
            payload={"tokens": {"prompt": "2", "completion": 3}, "elapsed_s": 1.5},
        ),
        TraceEvent(
            run_id="run-2",
            session_id="session-1",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": "bad", "completion": "", "total": "bad"},
                "elapsed_s": -1,
            },
        ),
        TraceEvent(
            run_id="run-3",
            session_id="session-2",
            event_type="agent_run_completed",
            payload={"tokens": {"prompt": 100, "completion": 100}, "elapsed_s": 100},
        ),
        TraceEvent(
            run_id="run-4",
            session_id="session-1",
            event_type="agent_run_failed",
            payload={"tokens": {"prompt": 100}, "elapsed_s": 100},
        ),
    ]
    monkeypatch.setattr(usage, "query_trace_events", lambda query: events)

    summary = usage.get_usage_summary(UsageQuery(session_id="session-1"))

    assert summary.run_count == 2
    assert summary.prompt_tokens == 2
    assert summary.completion_tokens == 3
    assert summary.total_tokens == 5
    assert summary.total_elapsed_s == 1.5
    assert summary.avg_elapsed_s == 0.75
    assert [(item.model, item.total_tokens) for item in summary.by_model] == [("unknown", 5)]
    assert not isnan(summary.total_elapsed_s)


def test_usage_summary_sorts_models_by_total_tokens_then_name(monkeypatch):
    from fleetent.observability import UsageQuery, usage

    events = [
        TraceEvent(
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"model_used": "zeta", "tokens": {"total": 5}},
        ),
        TraceEvent(
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"model_used": "alpha", "tokens": {"total": 5}},
        ),
        TraceEvent(
            run_id="run-3",
            event_type="agent_run_completed",
            payload={"model_used": "beta", "tokens": {"total": 8}},
        ),
    ]
    monkeypatch.setattr(usage, "query_trace_events", lambda query: events)

    summary = usage.get_usage_summary(UsageQuery())

    assert [(item.model, item.total_tokens) for item in summary.by_model] == [
        ("beta", 8),
        ("alpha", 5),
        ("zeta", 5),
    ]
