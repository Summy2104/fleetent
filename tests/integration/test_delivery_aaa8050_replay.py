"""Integration: AAA-8050 false-completion exposure via the fact trailer (§4.2).

Incident shape: the model claims "邮件已发 ✅ / 文件已上传 ✅" while no real fleetent
delivery of the file happened. With the trailer, the run's ground truth (only what
fleetent actually delivered) sits beside the model's claim — the gap exposes the false
completion instead of the model's self-report being the result. Equivalence replay at
the loop level (mock LLM + mock outbound); the live my-bot replay needs real Slack/MCP.
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
    cfg = MagicMock(model="m", max_tokens=512, params={}, fallbacks=())
    monkeypatch.setattr(
        loop_mod, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(loop_mod, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(loop_mod, "get_schemas", lambda: [])
    monkeypatch.setattr(loop_mod, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(loop_mod, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(loop_mod, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(loop_mod, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(loop_mod, "evaluate_risk_level", lambda name, args, ctx: "low")
    monkeypatch.setattr(loop_mod, "is_dynamic_risk", lambda name: False, raising=False)
    monkeypatch.setattr(
        loop_mod,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns or 50,
            max_consecutive_failures or 3,
        ),
    )
    return client


def _send_msg_then_claim_more(final_text: str):
    tc = MagicMock()
    tc.id = "tc1"
    tc.type = "function"
    tc.function.name = "send_im_message"
    tc.function.arguments = json.dumps({"target": "U2", "text": "通知"})
    m1 = MagicMock(content=None, tool_calls=[tc], refusal=None)
    m1.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "tc1",
                "type": "function",
                "function": {"name": "send_im_message", "arguments": tc.function.arguments},
            }
        ],
    }
    m2 = MagicMock(content=final_text, tool_calls=None, refusal=None)
    m2.model_dump.return_value = {"role": "assistant", "content": final_text}
    r1 = MagicMock(choices=[MagicMock(message=m1, finish_reason="tool_calls")], usage=MagicMock())
    r2 = MagicMock(choices=[MagicMock(message=m2, finish_reason="stop")], usage=MagicMock())
    seq = [r1, r2]
    n = [0]

    async def _create(**kwargs):
        r = seq[min(n[0], 1)]
        n[0] += 1
        return r

    return _create


async def test_false_file_claim_is_exposed_by_trailer(trace_db, mock_loop_env, monkeypatch):
    ok = DeliveryReceipt(ok=True, platform="slack", target="U1", target_type="user", kind="text")
    monkeypatch.setattr("fleetent.outbound.is_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr("fleetent.outbound.send_to", AsyncMock(return_value=ok))
    # The model sent a message, but ALSO claims it uploaded a file — which it never did.
    mock_loop_env.chat.completions.create = _send_msg_then_claim_more(
        "已通知对方，并已把报告文件上传给你 ✅（邮件已发、文件已上传）"
    )
    reply = await loop_mod.run(
        messages=[{"role": "user", "content": "通知并发文件"}],
        reply_func=AsyncMock(),
        session_id="sess-aaa8050",
        permission_gate_enabled=False,
        outbound_connectors={"slack": object()},
        session_context=SimpleNamespace(platform="slack", sender_id="U1", chat_type="dm"),
    )

    # The model's (partly false) claim is present...
    assert "文件已上传" in reply
    # ...but the system trailer reports ONLY what fleetent actually delivered: a message,
    # NO file. The gap between "文件已上传" and a trailer with no file exposes the false claim.
    assert "📬 实际投递" in reply
    assert "消息 1" in reply
    assert "文件 1" not in reply  # no file was actually delivered — claim unbacked
