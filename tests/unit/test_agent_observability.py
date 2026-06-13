"""Per-agent observability aggregation (task 6.x). Read-only consumer of traces.

The trace source is monkeypatched, so these are pure aggregation tests — no DB.
"""

from datetime import UTC, datetime

from fleetent.observability.traces import TraceEvent
from fleetent.platform.agent_management_console import agent_observability as obs


def _ev(event_type, payload, run_id="r1", ts="2026-06-02T00:00:00+00:00"):
    return TraceEvent(
        run_id=run_id,
        event_type=event_type,
        payload=payload,
        agent_name="ops-bot",
        session_id=run_id,
        ts=datetime.fromisoformat(ts),
    )


def _patch_events(monkeypatch, events):
    monkeypatch.setattr(obs, "query_trace_events", lambda query: iter(events))


def test_aggregate_computes_calls_tokens_latency_error_rate(monkeypatch):
    events = [
        _ev("agent_run_completed", {"elapsed_s": 2.0, "tokens": {"total": 100}}, run_id="r1"),
        _ev("agent_run_completed", {"elapsed_s": 4.0, "tokens": {"total": 300}}, run_id="r2"),
        _ev("agent_run_failed", {"error": "boom"}, run_id="r3"),
    ]
    _patch_events(monkeypatch, events)

    agg = obs.aggregate("ops-bot", window="24h", now=datetime(2026, 6, 2, 1, tzinfo=UTC))

    assert agg["agent_name"] == "ops-bot"
    assert agg["calls"] == 3  # 2 completed + 1 failed
    assert agg["tokens"] == 400
    assert agg["avg_latency"] == 3.0  # (2 + 4) / 2 completed
    assert round(agg["error_rate"], 3) == round(1 / 3, 3)


def test_aggregate_approval_pass_rate(monkeypatch):
    events = [
        _ev("permission_requested", {"tool_name": "shell"}, run_id="r1"),
        _ev("permission_resolved", {"decision": "approved"}, run_id="r1"),
        _ev("permission_requested", {"tool_name": "shell"}, run_id="r2"),
        _ev("permission_resolved", {"decision": "denied"}, run_id="r2"),
    ]
    _patch_events(monkeypatch, events)

    agg = obs.aggregate("ops-bot", window="24h", now=datetime(2026, 6, 2, 1, tzinfo=UTC))

    assert agg["approvals_triggered"] == 2
    assert agg["approval_pass_rate"] == 0.5


def test_aggregate_recent_sessions_listed(monkeypatch):
    events = [
        _ev("agent_run_completed", {"elapsed_s": 1.0}, run_id="r1", ts="2026-06-02T00:00:00+00:00"),
        _ev("agent_run_failed", {"error": "x"}, run_id="r2", ts="2026-06-02T00:30:00+00:00"),
    ]
    _patch_events(monkeypatch, events)

    agg = obs.aggregate("ops-bot", window="24h", now=datetime(2026, 6, 2, 1, tzinfo=UTC))
    recent = {s["run_id"]: s["status"] for s in agg["recent_sessions"]}
    assert recent == {"r1": "completed", "r2": "failed"}


def test_aggregate_empty_when_no_events(monkeypatch):
    _patch_events(monkeypatch, [])
    agg = obs.aggregate("ghost", window="24h", now=datetime(2026, 6, 2, 1, tzinfo=UTC))
    assert agg["calls"] == 0
    assert agg["error_rate"] == 0.0
    assert agg["approval_pass_rate"] is None
    assert agg["recent_sessions"] == []


def test_drill_down_returns_ordered_chain(monkeypatch):
    events = [
        _ev("agent_run_started", {}, run_id="r9", ts="2026-06-02T00:00:00+00:00"),
        _ev(
            "tool_call_started", {"tool_name": "shell"}, run_id="r9", ts="2026-06-02T00:00:01+00:00"
        ),
        _ev("agent_run_completed", {"elapsed_s": 1.0}, run_id="r9", ts="2026-06-02T00:00:02+00:00"),
    ]
    monkeypatch.setattr(obs, "query_trace_events", lambda query: iter(events))
    chain = obs.drill_down("r9")
    assert [e["event_type"] for e in chain] == [
        "agent_run_started",
        "tool_call_started",
        "agent_run_completed",
    ]
