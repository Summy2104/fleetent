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


# --- model / task_type distribution + binding facts (任务 3.1/3.2) ------------


def test_model_distribution_by_model_and_task_type():
    traces = [
        _t(model_used="gpt-4o", task_type="chat", total_tokens=100),
        _t(model_used="gpt-4o", task_type="chat", total_tokens=50),
        _t(model_used="claude", task_type="code", total_tokens=200),
    ]
    dist = s.model_distribution(traces)
    assert dist["by_model"]["gpt-4o"] == {"calls": 2, "total_tokens": 150}
    assert dist["by_task_type"]["code"] == {"calls": 1, "total_tokens": 200}


def test_binding_facts_counts_and_provenance():
    states = [
        {"agent_name": "a", "provenance": "managed"},
        {"agent_name": "b", "provenance": "adhoc"},
        {"agent_name": "c", "provenance": "adhoc"},
    ]
    facts = s.binding_facts(bindings=4, default_agent="a", states=states)
    assert facts["bindings"] == 4
    assert facts["default_agent"] == "a"
    assert facts["provenance"] == {"managed": 1, "adhoc": 2}


# --- dimension drill-down (任务 3.5/3.6) --------------------------------------


def test_slice_traces_combined_filters_converge():
    traces = [
        _t(user_id="u1", channel="c1", model_used="m1", ts="2026-06-01T00:00:00"),
        _t(user_id="u1", channel="c2", model_used="m1", ts="2026-06-02T00:00:00"),
        _t(user_id="u2", channel="c1", model_used="m2", ts="2026-06-03T00:00:00"),
    ]
    out = s.slice_traces(traces, user_id="u1", channel="c1")
    assert len(out) == 1 and out[0]["channel"] == "c1"
    # time window narrows further
    windowed = s.slice_traces(traces, since="2026-06-02T00:00:00", until="2026-06-02T23:59:59")
    assert [t["user_id"] for t in windowed] == ["u1"]


# --- ⏳ field readiness detection (任务 4.3/4.4) ------------------------------


def test_field_readiness_placeholder_until_present():
    traces = [_t(stop_reason="end_turn"), _t(elapsed_s=1.0)]
    readiness = s.field_readiness(traces, ["stop_reason", "error_class", "fallback"])
    assert readiness["stop_reason"] == "ready"  # present in at least one trace
    assert readiness["error_class"] == s.PENDING_DATA  # never emitted
    assert readiness["fallback"] == s.PENDING_DATA


# --- CSV export serialization (任务 8.1/8.2) ---------------------------------


def test_rows_to_csv_serializes_header_and_values():
    rows = [
        {"user_id": "u1", "total_tokens": 100, "calls": 2},
        {"user_id": "u2", "total_tokens": 50, "calls": 1},
    ]
    lines = s.rows_to_csv(rows).strip().splitlines()
    assert lines[0] == "user_id,total_tokens,calls"
    assert lines[1] == "u1,100,2"
    assert lines[2] == "u2,50,1"


def test_rows_to_csv_empty_returns_blank():
    assert s.rows_to_csv([]) == ""


# --- sub_agent degradation (任务 6.3/6.4) ------------------------------------


def test_expand_subagents_degraded_note_when_unlinkable():
    traces = [_t(session_id="s1", request_id="r1", ts="t0")]  # no children, no parent links
    stream = s.build_event_stream(traces, "r1")
    out = s.expand_subagents(stream, traces, note_when_empty=True)
    assert out["events"][0].get("sub_agent_chain") is None
    assert out.get("sub_agent_note") == "无法关联子链路"
