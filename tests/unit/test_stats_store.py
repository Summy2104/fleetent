"""Unit tests for stats_store pure aggregators (no DB / no IO)."""

from fleetent.platform.agent_statistics import stats_store as s


def _t(**kw):
    return {**kw}


def test_aggregate_usage():
    traces = [
        _t(
            user_id="u1",
            channel="c1",
            session_id="s1",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        _t(
            user_id="u2",
            channel="c1",
            session_id="s2",
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
        ),
    ]
    agg = s.aggregate_usage(traces)
    assert agg["calls"] == 2
    assert agg["users"] == 2
    assert agg["channels"] == 1
    assert agg["total_tokens"] == 45
    assert agg["avg_total_tokens"] == 22.5


def test_aggregate_usage_empty():
    assert s.aggregate_usage([])["calls"] == 0
    assert s.aggregate_usage([])["avg_total_tokens"] == 0


def test_performance_percentiles():
    traces = [_t(elapsed_s=v, rounds=2) for v in [1, 2, 3, 4, 100]]
    perf = s.aggregate_performance(traces)
    assert perf["latency_p50"] == 3.0
    assert perf["latency_p95"] >= 4.0
    assert perf["avg_rounds"] == 2.0


def test_top_tools_and_avg():
    traces = [
        _t(messages=[{"tool_calls": [{"name": "read_file"}, {"name": "search"}]}]),
        _t(messages=[{"tool_calls": [{"name": "read_file"}]}]),
    ]
    tt = s.top_tools(traces)
    assert tt["top"][0] == ("read_file", 2)
    assert tt["avg_tools_per_run"] == 1.5


def test_allowed_tools_coverage_flags_unused():
    traces = [_t(messages=[{"tool_calls": [{"name": "read_file"}]}])]
    cov = s.allowed_tools_coverage(traces, ["read_*", "github__*", "delete_db"])
    assert "read_*" not in cov["unused_patterns"]  # matched
    assert "github__*" in cov["unused_patterns"]
    assert "delete_db" in cov["unused_patterns"]


def test_allowed_tools_coverage_empty():
    assert s.allowed_tools_coverage([], ["read_*"])["unused_patterns"] == ["read_*"]


def test_approval_stats():
    approvals = [
        {"decision": "approved"},
        {"decision": "rejected"},
        {"decision": "timeout"},
        {"decision": "approved"},
    ]
    st = s.approval_stats(approvals)
    assert st["triggered"] == 4
    assert st["pass_rate"] == 0.5
    assert s.approval_stats([])["pass_rate"] is None


def test_compare_agents_stable_order():
    metrics = {"b": {"calls": 5}, "a": {"calls": 5}, "c": {"calls": 9}}
    ordered = s.compare_agents(metrics, "calls")
    assert [r["agent_id"] for r in ordered] == ["c", "a", "b"]  # 9 first, ties a<b


def test_per_user_ranking():
    traces = [
        _t(user_id="u1", total_tokens=100, ts="2026-06-01T10:00:00"),
        _t(user_id="u1", total_tokens=50, ts="2026-06-02T10:00:00"),
        _t(user_id="u2", total_tokens=10, ts="2026-06-01T10:00:00"),
    ]
    ranking = s.per_user_ranking(traces)
    assert ranking[0]["user_id"] == "u1"
    assert ranking[0]["total_tokens"] == 150
    assert ranking[0]["active_days"] == 2
    assert ranking[0]["last_active"] == "2026-06-02T10:00:00"


def test_cost_configured_and_unconfigured():
    traces = [
        _t(model_used="gpt", prompt_tokens=1000, completion_tokens=2000),
        _t(model_used="local", prompt_tokens=500, completion_tokens=500),
    ]
    pricing = {"gpt": {"input": 1.0, "output": 2.0}, "local": None}
    out = s.cost(traces, pricing)
    assert out["by_model"]["gpt"]["cost"] == 5.0  # 1*1 + 2*2
    assert out["by_model"]["local"]["cost"] == s.UNCONFIGURED


def test_cost_no_pricing_table_pending():
    out = s.cost([_t(model_used="x")], None)
    assert out["status"] == s.PENDING_DATA


def test_request_list_for_user_sorted():
    traces = [
        _t(user_id="u1", request_id="r2", ts="2026-06-02T00:00:00", total_tokens=5),
        _t(user_id="u1", request_id="r1", ts="2026-06-01T00:00:00", total_tokens=3),
        _t(user_id="u2", request_id="r3", ts="2026-06-01T00:00:00"),
    ]
    rows = s.build_request_list(traces, "u1")
    assert [r["request_id"] for r in rows] == ["r1", "r2"]


def test_event_stream_by_request_id():
    traces = [
        _t(request_id="r1", ts="2026-06-01T00:00:02", kind="reply"),
        _t(request_id="r1", ts="2026-06-01T00:00:01", kind="input"),
        _t(request_id="r2", ts="2026-06-01T00:00:00"),
    ]
    stream = s.build_event_stream(traces, "r1")
    assert [e["kind"] for e in stream["events"]] == ["input", "reply"]
    assert stream["complete"] is True


def test_event_stream_degraded_when_no_request_id():
    traces = [
        _t(session_id="sess", user_id="u1", ts="2026-06-01T00:00:01"),
        _t(session_id="sess", user_id="u1", ts="2026-06-01T00:00:00"),
    ]
    stream = s.build_event_stream_degraded(traces, "sess", "u1")
    assert stream["complete"] is False
    assert "request_id" in stream["note"]
    assert len(stream["events"]) == 2


def test_expand_subagents():
    traces = [
        _t(request_id="r1", session_id="parent", ts="2026-06-01T00:00:00"),
        _t(parent_session_id="parent", ts="2026-06-01T00:00:01", kind="child"),
    ]
    stream = s.build_event_stream(traces, "r1")
    s.expand_subagents(stream, traces)
    assert stream["events"][0]["sub_agent_chain"][0]["kind"] == "child"
