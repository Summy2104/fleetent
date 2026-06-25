"""Integration: tool_call trace events are emitted from the agent loop (both paths).

Drives the full ``loop.run`` / ``loop.run_stream`` with a mocked LLM and a mocked
dispatch, asserting a real tool execution writes one ``tool_call`` trace event (with
``failed`` and ``duration_ms``), a failed execution records ``failed=true``, and a
guardrail/approval placeholder records nothing — consistent across both paths.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as loop_mod
from fleetent.db import SQLiteDatabase
from fleetent.observability import TraceQuery, query_trace_events
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration.test_migrations import apply_migrations


@pytest.fixture
def trace_db(tmp_path, monkeypatch):
    db_path = tmp_path / "traces.db"
    apply_migrations(db_path)
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("fleetent.observability.traces._state_db", db)
    return db_path


@pytest.fixture
def mock_loop_env(monkeypatch):
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    monkeypatch.setattr(
        loop_mod, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(loop_mod, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(loop_mod, "get_schemas", lambda: [])
    monkeypatch.setattr(loop_mod, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(loop_mod, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(loop_mod, "log", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(loop_mod, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(loop_mod, "available_skills_prompt", lambda *a, **k: "")
    # get_risk_level feeds the trace's static "risk" field; evaluate_risk_level feeds the
    # gate decision (default low → ungated; reject-path tests override it below).
    monkeypatch.setattr(loop_mod, "get_risk_level", lambda name: "low")
    monkeypatch.setattr(loop_mod, "evaluate_risk_level", lambda name, args, ctx: "low")
    monkeypatch.setattr(
        loop_mod,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


def _two_turn_tool_then_stop(tool_name: str, arguments: dict):
    tc = MagicMock()
    tc.id = f"tc-{tool_name}"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(arguments)

    msg1 = MagicMock()
    msg1.content = None
    msg1.tool_calls = [tc]
    msg1.refusal = None
    # Real dict so message hygiene/sanitize on the next turn does not reject a MagicMock,
    # which would short-circuit the run before the completion trace is recorded.
    msg1.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"tc-{tool_name}",
                "type": "function",
                "function": {"name": tool_name, "arguments": json.dumps(arguments)},
            }
        ],
    }
    choice1 = MagicMock()
    choice1.message = msg1
    choice1.finish_reason = "tool_calls"
    resp1 = MagicMock()
    resp1.choices = [choice1]
    resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    msg2 = MagicMock()
    msg2.content = "done"
    msg2.tool_calls = None
    msg2.refusal = None
    msg2.model_dump.return_value = {"role": "assistant", "content": "done"}
    choice2 = MagicMock()
    choice2.message = msg2
    choice2.finish_reason = "stop"
    resp2 = MagicMock()
    resp2.choices = [choice2]
    resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    responses = [resp1, resp2]
    call_count = [0]

    async def _create(**kwargs):
        r = responses[min(call_count[0], len(responses) - 1)]
        call_count[0] += 1
        return r

    return _create


def _tool_calls(session_id: str):
    return list(query_trace_events(TraceQuery(session_id=session_id, event_type="tool_call")))


async def test_run_records_tool_call_on_real_execution(trace_db, mock_loop_env, monkeypatch):
    monkeypatch.setattr(loop_mod, "dispatch", AsyncMock(return_value="ok"))
    mock_loop_env.chat.completions.create = _two_turn_tool_then_stop("send_file", {"path": "/a"})

    await loop_mod.run(
        messages=[{"role": "user", "content": "go"}],
        reply_func=AsyncMock(),
        session_id="sess-run-ok",
        permission_gate_enabled=False,
    )

    events = _tool_calls("sess-run-ok")
    assert len(events) == 1
    payload = events[0].payload
    assert payload["tool_name"] == "send_file"
    assert payload["failed"] is False
    assert "duration_ms" in payload
    assert payload["risk"] == "low"


async def test_run_records_failed_true_on_tool_error(trace_db, mock_loop_env, monkeypatch):
    monkeypatch.setattr(loop_mod, "dispatch", AsyncMock(side_effect=RuntimeError("boom")))
    mock_loop_env.chat.completions.create = _two_turn_tool_then_stop("send_file", {})

    await loop_mod.run(
        messages=[{"role": "user", "content": "go"}],
        reply_func=AsyncMock(),
        session_id="sess-run-fail",
        permission_gate_enabled=False,
    )

    events = _tool_calls("sess-run-fail")
    assert len(events) == 1
    assert events[0].payload["failed"] is True


def _chunk(content=None, tool_call=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_call, reasoning_content=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)], usage=None
    )


def _tc_delta(tool_name: str, arguments: dict):
    return [
        SimpleNamespace(
            index=0,
            id=f"tc-{tool_name}",
            function=SimpleNamespace(name=tool_name, arguments=json.dumps(arguments)),
        )
    ]


async def test_run_stream_records_tool_call(trace_db, mock_loop_env, monkeypatch):
    monkeypatch.setattr(loop_mod, "dispatch", AsyncMock(return_value="ok"))
    cfg = SimpleNamespace(model="test-model", max_tokens=512, params={}, fallbacks=())
    policy = MagicMock()
    policy.resolve.return_value = (cfg,)
    monkeypatch.setattr(loop_mod, "_active_model_policy", lambda: policy)
    monkeypatch.setattr(loop_mod, "_select_policy_route", lambda messages, p: "default")
    monkeypatch.setattr(loop_mod, "build_context", AsyncMock(side_effect=RuntimeError("no kb")))

    turns = [
        [
            _chunk(tool_call=_tc_delta("read_file", {"path": "/b"})),
            _chunk(finish_reason="tool_calls"),
        ],
        [_chunk(content="done", finish_reason="stop")],
    ]
    call = [0]

    async def _fake_stream(policy, chain, messages, schemas, **kw):
        idx = min(call[0], len(turns) - 1)
        call[0] += 1
        chunks = turns[idx]

        async def _gen():
            for c in chunks:
                yield c

        return _gen(), cfg, messages

    monkeypatch.setattr(loop_mod, "_stream_with_overflow_retry", _fake_stream)

    async for _event in loop_mod.run_stream(
        user_input="go",
        session_id="sess-stream-ok",
    ):
        pass

    events = _tool_calls("sess-stream-ok")
    assert len(events) == 1
    assert events[0].payload["tool_name"] == "read_file"
    assert events[0].payload["failed"] is False


async def test_run_events_share_session_id_in_order(trace_db, mock_loop_env, monkeypatch):
    monkeypatch.setattr(loop_mod, "dispatch", AsyncMock(return_value="ok"))
    built = SimpleNamespace(
        text="ctx",
        sources=[
            SimpleNamespace(
                source_id="m1",
                source_type="memory",
                score=1.0,
                token_estimate=5,
                metadata={"memory_type": "fact"},
            )
        ],
    )
    monkeypatch.setattr(loop_mod, "build_context", AsyncMock(return_value=built))
    mock_loop_env.chat.completions.create = _two_turn_tool_then_stop("send_file", {"path": "/a"})

    await loop_mod.run(
        messages=[{"role": "user", "content": "go"}],
        reply_func=AsyncMock(),
        session_id="sess-seq",
        permission_gate_enabled=False,
    )

    events = list(query_trace_events(TraceQuery(session_id="sess-seq")))
    by_type = [e.event_type for e in events]
    assert "injected_context" in by_type
    assert "tool_call" in by_type
    assert "agent_run_completed" in by_type
    # every event of this run shares the session id
    assert {e.session_id for e in events} == {"sess-seq"}
    # time-ordered: context injected before the tool runs, completion last
    assert by_type.index("injected_context") < by_type.index("tool_call")
    assert by_type.index("tool_call") < by_type.index("agent_run_completed")


async def test_agent_run_completed_carries_session_id(trace_db, mock_loop_env, monkeypatch):
    monkeypatch.setattr(loop_mod, "dispatch", AsyncMock(return_value="ok"))
    mock_loop_env.chat.completions.create = _two_turn_tool_then_stop("send_file", {})

    await loop_mod.run(
        messages=[{"role": "user", "content": "go"}],
        reply_func=AsyncMock(),
        session_id="sess-complete",
        permission_gate_enabled=False,
    )

    completed = list(
        query_trace_events(TraceQuery(session_id="sess-complete", event_type="agent_run_completed"))
    )
    assert len(completed) == 1
    assert completed[0].session_id == "sess-complete"


async def test_resumed_approval_records_tool_call_for_session(trace_db, monkeypatch):
    import fleetent.runtime.approval_resume as ar
    from fleetent.runtime.approval_resume import resume_pending_approval
    from fleetent.tools.registry import ToolContext

    entry = {
        "approval_id": "a1",
        "tool_call_id": "tc_1",
        "tool_name": "send_file",
        "tool_args": {"path": "/a"},
        "risk": "medium",
    }
    monkeypatch.setattr(ar.session_mgr, "get_pending_approval", AsyncMock(return_value=dict(entry)))
    monkeypatch.setattr(ar.session_mgr, "remove_pending_approval", AsyncMock())
    monkeypatch.setattr(ar, "dispatch", lambda name, args, **kw: "ok")
    monkeypatch.setattr(ar, "get_risk_level", lambda name: "medium", raising=False)

    ctx = ToolContext(session_id="sess-resume", agent_name="bot")

    async def continue_run(msgs):
        return "done"

    await resume_pending_approval(
        session_id="sess-resume",
        approval_id="a1",
        decision="approved",
        messages=[],
        tool_context=ctx,
        continue_run=continue_run,
    )

    events = list(query_trace_events(TraceQuery(session_id="sess-resume", event_type="tool_call")))
    assert len(events) == 1
    assert events[0].payload["tool_name"] == "send_file"
    assert events[0].payload["failed"] is False
    assert events[0].session_id == "sess-resume"


async def test_rejected_placeholder_records_no_tool_call(trace_db, mock_loop_env, monkeypatch):
    # critical risk → Action Gate rejects, the slot becomes a placeholder, dispatch
    # never runs, and no tool_call event is recorded.
    monkeypatch.setattr(loop_mod, "evaluate_risk_level", lambda name, args, ctx: "critical")
    dispatch = AsyncMock(return_value="ok")
    monkeypatch.setattr(loop_mod, "dispatch", dispatch)
    mock_loop_env.chat.completions.create = _two_turn_tool_then_stop("nuke", {})

    await loop_mod.run(
        messages=[{"role": "user", "content": "go"}],
        reply_func=AsyncMock(),
        session_id="sess-rejected",
        permission_gate_enabled=True,
    )

    dispatch.assert_not_called()
    assert _tool_calls("sess-rejected") == []
