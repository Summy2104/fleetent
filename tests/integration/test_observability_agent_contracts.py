from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as agent_loop
from fleetent.agent_config import AgentModels, ModelRouteEntry, ModelTarget
from fleetent.db import SQLiteDatabase
from fleetent.identity import Principal
from fleetent.long_term_ctx import BuiltContext, ContextSource
from fleetent.model import ModelPolicySnapshot
from fleetent.observability import (
    TraceEvent,
    TraceQuery,
    UsageQuery,
    get_usage_summary,
    query_trace_events,
)
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration.test_migrations import apply_migrations


@pytest.fixture
def trace_db(tmp_path, monkeypatch):
    db_path = tmp_path / "observability_contracts.db"
    apply_migrations(db_path)
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("fleetent.observability.traces._state_db", db)
    return db_path


@pytest.fixture
def agent_runtime(monkeypatch):
    client = AsyncMock()
    client.model_policy = ModelPolicySnapshot.from_models(
        agent_id="agent-contract",
        models=AgentModels(
            targets=[
                ModelTarget(
                    id="primary",
                    provider="test",
                    protocol="openai_chat",
                    base_url="http://example.test/v1",
                    model="contract-model",
                )
            ],
            routes={"default": [ModelRouteEntry(target="primary", max_tokens=512)]},
        ),
    )
    monkeypatch.setattr(agent_loop, "_build_async_client", lambda *a, **k: client)
    monkeypatch.setattr(agent_loop, "get_schemas", lambda: [])
    monkeypatch.setattr(agent_loop, "maybe_compress", lambda messages, **kwargs: messages)
    monkeypatch.setattr(agent_loop, "match_skill", lambda _: None)
    monkeypatch.setattr(agent_loop, "run_pipeline_from_conversation", AsyncMock())
    return client


def _text_response(
    text: str = "contract reply",
    *,
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
) -> MagicMock:
    message = MagicMock()
    message.content = text
    message.tool_calls = None
    message.model_dump.return_value = {"role": "assistant", "content": text}

    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


async def _stream_chunks(
    *contents: str,
    prompt_tokens: int = 13,
    completion_tokens: int = 5,
) -> AsyncIterator[MagicMock]:
    for index, content in enumerate(contents):
        chunk = MagicMock()
        chunk.usage = None
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = content
        chunk.choices[0].delta.tool_calls = None
        chunk.choices[0].finish_reason = "stop" if index == len(contents) - 1 else None
        yield chunk

    usage_chunk = MagicMock()
    usage_chunk.choices = []
    usage_chunk.usage = MagicMock()
    usage_chunk.usage.prompt_tokens = prompt_tokens
    usage_chunk.usage.completion_tokens = completion_tokens
    usage_chunk.usage.total_tokens = prompt_tokens + completion_tokens
    yield usage_chunk


def _contract_context() -> BuiltContext:
    return BuiltContext(
        text="Remember private deployment preferences",
        sources=[
            ContextSource(
                source_type="memory",
                source_id="memory-1",
                score=0.91,
                metadata={"type": "preference"},
            )
        ],
    )


def _safety_context() -> BuiltContext:
    return BuiltContext(
        text="Use summarized source material",
        sources=[
            ContextSource(
                source_type="knowledge",
                source_id="chunk-1",
                score=0.82,
                metadata={
                    "kb_id": "kb-1",
                    "content": "raw source content must not be stored",
                    "text": "raw source text must not be stored",
                    "transcript": "raw source transcript must not be stored",
                    "bot_token": "xoxb-sensitive-token",
                    "owner_email": "alice@example.com",
                    "owner_phone": "13800138000",
                    "large_note": "x" * 5000,
                },
            )
        ],
    )


def _events_for_single_run() -> list[TraceEvent]:
    events = list(query_trace_events(TraceQuery()))
    run_ids = {event.run_id for event in events}
    assert len(run_ids) == 1
    return events


async def test_non_streaming_run_persists_context_and_completion_trace_contract(
    trace_db, agent_runtime, monkeypatch
):
    agent_runtime.chat.completions.create = AsyncMock(return_value=_text_response("done"))
    monkeypatch.setattr(
        agent_loop,
        "build_context",
        AsyncMock(return_value=_contract_context()),
    )

    reply = await agent_loop.run(
        [{"role": "user", "content": "What should I deploy?"}],
        principal=Principal(user_id="user-contract", tenant_id="default"),
        agent_name="agent-contract",
        model_policy=agent_runtime.model_policy,
    )

    assert reply == "done"
    events = _events_for_single_run()
    injected = next(event for event in events if event.event_type == "injected_context")
    completed = next(event for event in events if event.event_type == "agent_run_completed")
    assert injected.run_id == completed.run_id

    assert list(
        query_trace_events(TraceQuery(run_id=completed.run_id, event_type="injected_context"))
    ) == [injected]
    assert list(
        query_trace_events(TraceQuery(run_id=completed.run_id, event_type="agent_run_completed"))
    ) == [completed]
    assert injected.payload["sources"][0]["source_id"] == "memory-1"
    assert completed.payload["model_used"] == "contract-model"
    assert completed.payload["tokens"] == {"prompt": 11, "completion": 7, "total": 18}


async def test_streaming_run_persists_context_and_completion_trace_contract(
    trace_db, agent_runtime, monkeypatch
):
    agent_runtime.chat.completions.create = AsyncMock(
        return_value=_stream_chunks("stream ", "done")
    )
    monkeypatch.setattr(
        agent_loop,
        "build_context",
        AsyncMock(return_value=_contract_context()),
    )

    stream_events = [
        event
        async for event in agent_loop.run_stream(
            "What should I deploy?",
            principal=Principal(user_id="user-contract", tenant_id="default"),
            agent_name="agent-contract",
            model_policy=agent_runtime.model_policy,
        )
    ]

    assert stream_events[-1] == {"type": "done", "content": "stream done"}
    events = _events_for_single_run()
    injected = next(event for event in events if event.event_type == "injected_context")
    completed = next(event for event in events if event.event_type == "agent_run_completed")
    assert injected.run_id == completed.run_id

    assert list(
        query_trace_events(TraceQuery(run_id=completed.run_id, event_type="injected_context"))
    ) == [injected]
    assert list(
        query_trace_events(TraceQuery(run_id=completed.run_id, event_type="agent_run_completed"))
    ) == [completed]
    assert injected.payload["sources"][0]["source_id"] == "memory-1"
    assert completed.payload["reply"] == "stream done"
    assert completed.payload["tokens"] == {"prompt": 13, "completion": 5, "total": 18}


async def test_source_attribution_payload_excludes_raw_content_and_is_sanitized(
    trace_db, agent_runtime, monkeypatch
):
    agent_runtime.chat.completions.create = AsyncMock(return_value=_text_response("done"))
    monkeypatch.setattr(
        agent_loop,
        "build_context",
        AsyncMock(return_value=_safety_context()),
    )

    await agent_loop.run(
        [{"role": "user", "content": "Find deployment notes"}],
        principal=Principal(user_id="user-contract", tenant_id="default"),
        agent_name="agent-contract",
        model_policy=agent_runtime.model_policy,
    )

    injected = next(query_trace_events(TraceQuery(event_type="injected_context")))
    raw_payload = json.dumps(injected.payload)
    source = injected.payload["sources"][0]
    metadata = source["metadata"]

    assert "raw source content must not be stored" not in raw_payload
    assert "raw source text must not be stored" not in raw_payload
    assert "raw source transcript must not be stored" not in raw_payload
    assert {"content", "text", "transcript"}.isdisjoint(metadata)

    assert "xoxb-sensitive-token" not in raw_payload
    assert "alice@example.com" not in raw_payload
    assert "13800138000" not in raw_payload
    assert metadata["bot_token"] == "[REDACTED:token]"
    assert metadata["owner_email"] == "[REDACTED:email]"
    assert metadata["owner_phone"] == "[REDACTED:phone]"

    assert injected.payload["truncated"] is True
    assert metadata["large_note"]["truncated"] is True
    assert metadata["large_note"]["original_length"] == 5000
    assert len(metadata["large_note"]["value"]) < 5000


async def test_usage_summary_counts_only_completion_events_when_context_is_injected(
    trace_db, agent_runtime, monkeypatch
):
    agent_runtime.chat.completions.create = AsyncMock(
        return_value=_text_response(
            "done",
            prompt_tokens=23,
            completion_tokens=17,
        )
    )
    monkeypatch.setattr(
        agent_loop,
        "build_context",
        AsyncMock(return_value=_contract_context()),
    )

    await agent_loop.run(
        [{"role": "user", "content": "What should I deploy?"}],
        principal=Principal(user_id="user-contract", tenant_id="default"),
        agent_name="agent-contract",
        model_policy=agent_runtime.model_policy,
    )

    assert len(list(query_trace_events(TraceQuery(event_type="injected_context")))) == 1
    assert len(list(query_trace_events(TraceQuery(event_type="agent_run_completed")))) == 1

    summary = get_usage_summary(
        UsageQuery(user_id="user-contract", agent_name="agent-contract", tenant_id="default")
    )

    assert summary.run_count == 1
    assert summary.prompt_tokens == 23
    assert summary.completion_tokens == 17
    assert summary.total_tokens == 40
    assert summary.by_model[0].model == "contract-model"
    assert summary.by_model[0].run_count == 1
    assert summary.by_model[0].total_tokens == 40
