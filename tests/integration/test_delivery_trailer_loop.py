"""Integration: delivery fact-trailer injection in the agent loop (§3.3, D4).

Drives loop.run with a mocked LLM that calls send_im_message then replies; the run's real
delivery ledger (populated by the tool) renders a fact trailer that is appended AFTER the
model's text in the returned reply — and absent when no outbound attempt was made.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as loop_mod
from fleetent.db import SQLiteDatabase
from fleetent.outbound import DeliveryReceipt
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
    monkeypatch.setattr(loop_mod, "extract_and_update", AsyncMock())
    monkeypatch.setattr(loop_mod, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(loop_mod, "evaluate_risk_level", lambda name, args, ctx: "low")
    monkeypatch.setattr(loop_mod, "is_dynamic_risk", lambda name: False, raising=False)
    monkeypatch.setattr(
        loop_mod,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


def _tool_then_stop(tool_name: str, arguments: dict, final_text: str):
    tc = MagicMock()
    tc.id = f"tc-{tool_name}"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(arguments)
    msg1 = MagicMock()
    msg1.content = None
    msg1.tool_calls = [tc]
    msg1.refusal = None
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
    choice1 = MagicMock(message=msg1, finish_reason="tool_calls")
    resp1 = MagicMock(choices=[choice1], usage=MagicMock(prompt_tokens=1, completion_tokens=1))
    msg2 = MagicMock()
    msg2.content = final_text
    msg2.tool_calls = None
    msg2.refusal = None
    msg2.model_dump.return_value = {"role": "assistant", "content": final_text}
    choice2 = MagicMock(message=msg2, finish_reason="stop")
    resp2 = MagicMock(choices=[choice2], usage=MagicMock(prompt_tokens=1, completion_tokens=1))
    responses = [resp1, resp2]
    n = [0]

    async def _create(**kwargs):
        r = responses[min(n[0], len(responses) - 1)]
        n[0] += 1
        return r

    return _create


async def test_reply_gets_delivery_trailer_after_outbound(trace_db, mock_loop_env, monkeypatch):
    ok = DeliveryReceipt(ok=True, platform="slack", target="U999", target_type="user", kind="text")
    monkeypatch.setattr("fleetent.outbound.is_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr("fleetent.outbound.send_to", AsyncMock(return_value=ok))
    mock_loop_env.chat.completions.create = _tool_then_stop(
        "send_im_message", {"target": "U999", "text": "通知你"}, "已通知，全部完成 ✅"
    )

    reply = await loop_mod.run(
        messages=[{"role": "user", "content": "通知 U999"}],
        reply_func=AsyncMock(),
        session_id="sess-trailer",
        permission_gate_enabled=False,
        outbound_connectors={"slack": object()},
        session_context=SimpleNamespace(platform="slack", sender_id="U1", chat_type="dm"),
    )

    assert "已通知，全部完成" in reply  # the model's text is preserved
    assert "📬 实际投递" in reply  # the system trailer is appended after it
    assert "消息 1" in reply
    assert reply.index("📬") > reply.index("已通知")  # trailer comes AFTER model text


async def test_no_outbound_no_trailer(trace_db, mock_loop_env, monkeypatch):
    # A plain Q&A turn with no outbound attempt → zero-noise: no trailer.
    msg = MagicMock()
    msg.content = "答案是 42"
    msg.tool_calls = None
    msg.refusal = None
    msg.model_dump.return_value = {"role": "assistant", "content": "答案是 42"}
    resp = MagicMock(choices=[MagicMock(message=msg, finish_reason="stop")], usage=MagicMock())
    mock_loop_env.chat.completions.create = AsyncMock(return_value=resp)

    reply = await loop_mod.run(
        messages=[{"role": "user", "content": "几"}],
        reply_func=AsyncMock(),
        session_id="sess-no-trailer",
        permission_gate_enabled=False,
    )
    assert "答案是 42" in reply
    assert "📬" not in reply
