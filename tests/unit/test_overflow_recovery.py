"""Unit tests: reactive context-overflow recovery in the agent loop (C3b).

Tests the overflow retry helpers directly (no real LLM, no driving full run()).
"""

from __future__ import annotations

import httpx
import pytest
from openai import APIStatusError

import fleetent.runtime.loop as loop

_REQ = httpx.Request("POST", "http://x/v1/chat/completions")


def _overflow_error() -> APIStatusError:
    return APIStatusError(
        "ctx",
        response=httpx.Response(status_code=400, request=_REQ),
        body={"message": "maximum context length", "code": "context_length_exceeded"},
    )


def _msgs() -> list[dict]:
    return [
        {"role": "user", "content": "x" * 400},
        {"role": "assistant", "content": "y" * 400},
        {"role": "user", "content": "z" * 400},
    ]


async def test_overflow_retry_compresses_and_retries(monkeypatch):
    calls = {"n": 0}

    async def fake_call(policy, chain, messages, schemas):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _overflow_error()
        return ("RESP", "CFG")

    monkeypatch.setattr(loop, "_call_policy_chat", fake_call)
    monkeypatch.setattr(loop, "compress_for_context_overflow", lambda msgs, **kw: msgs[:1])

    msgs = _msgs()
    resp, cfg = await loop._call_with_overflow_retry(
        object(), (), msgs, [], session_id="s", user_id="u", agent_name="a"
    )
    assert resp == "RESP"
    assert calls["n"] == 2
    assert msgs == [{"role": "user", "content": "x" * 400}]  # compressed in place


async def test_non_overflow_error_propagates(monkeypatch):
    async def fake_call(policy, chain, messages, schemas):
        raise ValueError("not overflow")

    monkeypatch.setattr(loop, "_call_policy_chat", fake_call)
    with pytest.raises(ValueError):
        await loop._call_with_overflow_retry(
            object(), (), _msgs(), [], session_id=None, user_id=None, agent_name=None
        )


async def test_overflow_guard_gives_up_when_no_progress(monkeypatch):
    async def fake_call(policy, chain, messages, schemas):
        raise _overflow_error()

    monkeypatch.setattr(loop, "_call_policy_chat", fake_call)
    # compression makes no progress (returns an equivalent-length list)
    monkeypatch.setattr(loop, "compress_for_context_overflow", lambda msgs, **kw: list(msgs))

    with pytest.raises(APIStatusError):
        await loop._call_with_overflow_retry(
            object(), (), _msgs(), [], session_id=None, user_id=None, agent_name=None
        )


async def test_overflow_retry_capped(monkeypatch):
    calls = {"n": 0}

    async def fake_call(policy, chain, messages, schemas):
        calls["n"] += 1
        raise _overflow_error()  # always overflows

    monkeypatch.setattr(loop, "_call_policy_chat", fake_call)
    # always makes progress, but the call never succeeds → cap must stop it
    monkeypatch.setattr(
        loop, "compress_for_context_overflow", lambda msgs, **kw: msgs[: max(1, len(msgs) - 1)]
    )

    with pytest.raises(APIStatusError):
        await loop._call_with_overflow_retry(
            object(), (), _msgs(), [], session_id=None, user_id=None, agent_name=None
        )
    assert calls["n"] == 2  # initial + 1 retry (cap), then give up


async def test_stream_overflow_retry_compresses_and_retries(monkeypatch):
    calls = {"n": 0}

    async def fake_stream(policy, chain, messages, schemas):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _overflow_error()
        return ("STREAM", "CFG")

    monkeypatch.setattr(loop, "_stream_policy_chat", fake_stream)
    monkeypatch.setattr(loop, "compress_for_context_overflow", lambda msgs, **kw: msgs[:1])

    stream, cfg, new_msgs = await loop._stream_with_overflow_retry(
        object(), (), _msgs(), [], session_id="s", user_id="u", agent_name="a"
    )
    assert stream == "STREAM"
    assert calls["n"] == 2
    assert new_msgs == [{"role": "user", "content": "x" * 400}]  # compressed (rebound list)


async def test_stream_non_overflow_error_propagates(monkeypatch):
    async def fake_stream(policy, chain, messages, schemas):
        raise ValueError("not overflow")

    monkeypatch.setattr(loop, "_stream_policy_chat", fake_stream)
    with pytest.raises(ValueError):
        await loop._stream_with_overflow_retry(
            object(), (), _msgs(), [], session_id=None, user_id=None, agent_name=None
        )
