from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import fleetent.agent_loop as agent_loop
from fleetent.intelligence.long_term_ctx import BuiltContext, ContextSource
from fleetent.model_router import RouteConfig


def _text_response(text: str = "ok") -> MagicMock:
    message = MagicMock()
    message.content = text
    message.tool_calls = None
    message.model_dump.return_value = {"role": "assistant", "content": text}

    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.usage = None
    return response


async def test_agent_runtime_calls_long_term_context_builder_with_existing_signature(
    monkeypatch,
):
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_text_response())
    cfg = RouteConfig(
        base_url="http://example.test/v1",
        model="test-model",
        api_key_env="TEST_API_KEY",
        max_tokens=321,
        fallbacks=(),
    )
    build_context = AsyncMock(return_value=BuiltContext(text="", sources=[]))

    monkeypatch.setattr(agent_loop, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(agent_loop, "get_schemas", lambda: [])
    monkeypatch.setattr(agent_loop, "maybe_compress", lambda messages: messages)
    monkeypatch.setattr(agent_loop, "match_skill", lambda _: None)
    monkeypatch.setattr(agent_loop, "build_context", build_context)
    monkeypatch.setattr(agent_loop, "record_trace_event", lambda event: None)
    monkeypatch.setattr(agent_loop, "record_injected_context", lambda run_id, sources: None)

    await agent_loop.run(
        [{"role": "user", "content": "what should I use?"}],
        user_id="user-1",
        agent_name="agent-1",
    )

    build_context.assert_awaited_once_with(
        "user-1",
        "what should I use?",
        "agent-1",
        321,
    )


def test_injected_context_trace_receives_budget_token_estimates(monkeypatch):
    captured = []
    monkeypatch.setattr(
        agent_loop,
        "record_injected_context",
        lambda run_id, sources: captured.append((run_id, sources)),
    )
    source = ContextSource(
        source_type="memory",
        source_id="mem-1",
        score=1.0,
        metadata={"type": "preference"},
        token_estimate=17,
    )

    agent_loop._record_injected_context("run-1", [source])

    assert captured[0][0] == "run-1"
    assert captured[0][1][0].token_estimate == 17
