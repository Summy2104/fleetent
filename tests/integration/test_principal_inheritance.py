"""Integration: internal calls inherit the parent/turn Principal (identity-port「继承」).

- sub_agent派生 inherits the parent run's full Principal (tenant_id, not hardcoded
  "default").
- invoke_agent passes the current turn's Principal through to the called agent run.

These exercise loop ↔ sub_agent / tools ↔ runtime collaboration with a mocked LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import fleetent.runtime.loop as al
from fleetent.identity import Principal


def _tool_resp(name: str, args: str = "{}", call_id: str = "tc-1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = args
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }
    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


def _text_resp(text: str = "done") -> MagicMock:
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None
    msg.model_dump = lambda: {"role": "assistant", "content": text}
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


@pytest.fixture
def mock_client(monkeypatch) -> AsyncMock:
    """Patch agent_loop external I/O; return the mock LLM client."""
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    monkeypatch.setattr(
        al, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(al, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(al, "_backoff_delay", lambda attempt, exc: 0.0, raising=False)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


async def test_sub_agent_inherits_parent_tenant(mock_client):
    """Task 2.1: parent run tenant T1 → sub_agent's parent_principal.tenant_id == T1."""
    from fleetent.runtime.sub_agent import SubAgentResult

    tasks_json = '[{"name": "t1", "prompt": "do it"}]'
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_resp(
                "sub_agent", f'{{"tasks": "{tasks_json.replace(chr(34), chr(92) + chr(34))}"}}'
            ),
            _text_resp("all done"),
        ]
    )
    fake_results = [SubAgentResult(name="t1", result="r", error=None, parent_session_id="")]

    parent = Principal(user_id="u-t1", tenant_id="T1")
    with patch.object(al, "SubAgentExecutor") as mock_executor_cls:
        mock_instance = AsyncMock()
        mock_instance.run = AsyncMock(return_value=fake_results)
        mock_executor_cls.return_value = mock_instance
        result = await al.run([{"role": "user", "content": "go"}], principal=parent)

    assert result == "all done"
    call_kwargs = mock_instance.run.call_args[1]
    assert call_kwargs["parent_principal"] == Principal(user_id="u-t1", tenant_id="T1")


async def test_invoke_agent_passes_turn_principal():
    """Task 2.3: invoke_agent forwards the current turn's Principal to the called run."""
    from fleetent.tools import builtin_tools
    from fleetent.tools.registry import ToolContext

    snapshot = MagicMock()
    snapshot.system_prompt = "sys"
    snapshot.allowed_tools = ["web_search"]
    snapshot.model_policy = MagicMock()

    captured: dict = {}

    async def fake_run(messages, **kwargs):
        captured["principal"] = kwargs.get("principal", "NOT_SET")
        return "child reply"

    turn_principal = Principal(user_id="u-t1", tenant_id="T1")
    ctx = ToolContext(agent_name="parent", principal=turn_principal)

    with (
        patch("fleetent.runtime.load_active", return_value=snapshot),
        patch("fleetent.runtime.loop.run", side_effect=fake_run),
    ):
        reply = await builtin_tools.invoke_agent("child", "hello", tool_context=ctx)

    assert reply == "child reply"
    assert captured["principal"] == Principal(user_id="u-t1", tenant_id="T1")
