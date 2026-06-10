from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import fleetent.runtime.loop as agent_loop
from fleetent.identity import Principal
from fleetent.agent_config import AgentModels, ModelRouteEntry, ModelTarget
from fleetent.long_term_ctx import BuiltContext, ContextSource
from fleetent.model import ModelPolicySnapshot


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
    policy = ModelPolicySnapshot.from_models(
        agent_id="agent-1",
        models=AgentModels(
            targets=[
                ModelTarget(
                    id="primary",
                    provider="test",
                    protocol="openai_chat",
                    base_url="http://example.test/v1",
                    model="test-model",
                )
            ],
            routes={"default": [ModelRouteEntry(target="primary", max_tokens=321)]},
        ),
    )
    build_context = AsyncMock(return_value=BuiltContext(text="", sources=[]))

    monkeypatch.setattr(agent_loop, "_build_async_client", lambda *a, **k: client)
    monkeypatch.setattr(agent_loop, "get_schemas", lambda: [])
    monkeypatch.setattr(agent_loop, "maybe_compress", lambda messages, **kwargs: messages)
    monkeypatch.setattr(agent_loop, "match_skill", lambda _: None)
    monkeypatch.setattr(agent_loop, "extract_and_update", AsyncMock())
    monkeypatch.setattr(agent_loop, "build_context", build_context)
    monkeypatch.setattr(agent_loop, "record_trace_event", lambda event: None)
    monkeypatch.setattr(agent_loop, "record_injected_context", lambda run_id, sources: None)

    await agent_loop.run(
        [{"role": "user", "content": "what should I use?"}],
        principal=Principal(user_id="user-1", tenant_id="default"),
        agent_name="agent-1",
        model_policy=policy,
    )

    # The parameter-style agent_loop passes the four positional args; memory_namespace
    # is left to build_context's own "default" (per-agent namespacing is not threaded
    # through the param-style run path chosen during the next<-main integration).
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
