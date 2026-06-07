"""Unit tests: same-target transient-error backoff retry (T2-1).

Tests the retry helper directly with a patched (zero) backoff so no real waits.
"""

from __future__ import annotations

import httpx
import pytest
from openai import APIStatusError, RateLimitError

import fleetent.runtime.loop as loop

_REQ = httpx.Request("POST", "http://x/v1/chat/completions")


def _429() -> RateLimitError:
    return RateLimitError("rate", response=httpx.Response(status_code=429, request=_REQ), body=None)


def _overflow() -> APIStatusError:
    return APIStatusError(
        "ctx",
        response=httpx.Response(status_code=400, request=_REQ),
        body={"message": "max context", "code": "context_length_exceeded"},
    )


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(loop, "_backoff_delay", lambda attempt, exc: 0.0)


async def test_transient_retry_then_succeeds():
    calls = {"n": 0}

    async def do_call():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _429()
        return "ok"

    assert await loop._create_with_transient_retry(do_call) == "ok"
    assert calls["n"] == 2


async def test_non_transient_error_not_retried():
    async def do_call():
        raise ValueError("nope")  # unknown → should_retry False

    with pytest.raises(ValueError):
        await loop._create_with_transient_retry(do_call)


async def test_transient_retry_capped():
    calls = {"n": 0}

    async def do_call():
        calls["n"] += 1
        raise _429()  # always

    with pytest.raises(RateLimitError):
        await loop._create_with_transient_retry(do_call)
    assert calls["n"] == loop._MAX_TRANSIENT_RETRIES + 1  # initial + capped retries


async def test_context_overflow_not_retried_here():
    calls = {"n": 0}

    async def do_call():
        calls["n"] += 1
        raise _overflow()  # should_retry True but should_compress True → excluded

    with pytest.raises(APIStatusError):
        await loop._create_with_transient_retry(do_call)
    assert calls["n"] == 1  # not retried (overflow handled elsewhere)
