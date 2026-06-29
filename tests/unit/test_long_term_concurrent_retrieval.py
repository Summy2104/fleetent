"""Unit tests: concurrent + timeout-bounded retrieval in build_context."""

from __future__ import annotations

import asyncio
import time

import pytest

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.config import LongTermContextSettings

# ── Task 1: config ────────────────────────────────────────────────────────────


def test_retrieval_timeout_default_is_5s() -> None:
    assert LongTermContextSettings().retrieval_timeout_seconds == 5.0


def test_retrieval_timeout_is_configurable() -> None:
    s = LongTermContextSettings(retrieval_timeout_seconds=0.1)
    assert s.retrieval_timeout_seconds == 0.1


@pytest.fixture(autouse=True)
def _publish_kb_enabled_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(
            agents={
                "agent-1": AgentFile(
                    name="agent-1",
                    version=1,
                    models=default_models(),
                    knowledge={
                        "enabled": True,
                        "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
                    },
                )
            },
            default="agent-1",
        ),
    )


# ── Task 2: single-path timeout/degrade helper ────────────────────────────────


async def test_helper_passes_through_normal_result() -> None:
    from fleetent import long_term_ctx

    async def _ok():
        return ["a", "b"]

    out = await long_term_ctx._retrieve_with_timeout("memory", _ok, timeout=1.0, empty=[])
    assert out == ["a", "b"]


async def test_helper_degrades_on_timeout() -> None:
    from fleetent import long_term_ctx

    async def _slow():
        await asyncio.sleep(1.0)
        return ["never"]

    out = await long_term_ctx._retrieve_with_timeout("memory", _slow, timeout=0.02, empty=[])
    assert out == []  # timed out → degraded to the empty sentinel, no raise


async def test_helper_degrades_on_exception() -> None:
    from fleetent import long_term_ctx

    async def _boom():
        raise RuntimeError("backend down")

    out = await long_term_ctx._retrieve_with_timeout("agent_memory", _boom, timeout=1.0, empty=[])
    assert out == []  # non-timeout exception → degraded, no raise


# ── Task 3: build_context concurrency ─────────────────────────────────────────


def _patch_three_paths(monkeypatch, long_term_ctx, *, mem, know, amem):
    """Patch the three retrieval paths with the given async callables."""
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", mem)
    monkeypatch.setattr(long_term_ctx.agent_memory, "search_agent_memory", amem)
    long_term_ctx.set_knowledge_provider(know)


async def test_three_paths_run_concurrently(monkeypatch) -> None:
    from fleetent import long_term_ctx

    delay = 0.15

    async def _mem(*a, **k):
        await asyncio.sleep(delay)
        return []

    async def _know(*a, **k):
        await asyncio.sleep(delay)
        return []

    async def _amem(*a, **k):
        await asyncio.sleep(delay)
        return []

    _patch_three_paths(monkeypatch, long_term_ctx, mem=_mem, know=_know, amem=_amem)

    started = time.monotonic()
    await long_term_ctx.build_context("u1", "q", "agent-1", available_tokens=500)
    elapsed = time.monotonic() - started
    # Concurrent ≈ one path (delay), not the sum (3×delay). Generous upper bound.
    assert elapsed < delay * 2.5


async def test_one_path_timeout_others_still_included(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from fleetent import long_term_ctx
    from fleetent.config import LongTermContextSettings

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: LongTermContextSettings(retrieval_timeout_seconds=0.05),
    )

    async def _slow_mem(*a, **k):
        await asyncio.sleep(1.0)
        return []

    know = AsyncMock(return_value=[])
    amem = AsyncMock(return_value=[])
    _patch_three_paths(monkeypatch, long_term_ctx, mem=_slow_mem, know=know, amem=amem)

    # Memory times out; build_context must still return (not raise, not hang).
    result = await long_term_ctx.build_context("u1", "q", "agent-1", available_tokens=500)
    assert result is not None
    know.assert_awaited()  # other paths still ran
    amem.assert_awaited()


async def test_all_paths_timeout_returns_empty_context(monkeypatch) -> None:
    from fleetent import long_term_ctx
    from fleetent.config import LongTermContextSettings

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: LongTermContextSettings(retrieval_timeout_seconds=0.05),
    )

    async def _slow(*a, **k):
        await asyncio.sleep(1.0)
        return []

    _patch_three_paths(monkeypatch, long_term_ctx, mem=_slow, know=_slow, amem=_slow)

    result = await long_term_ctx.build_context("u1", "q", "agent-1", available_tokens=500)
    assert result.text == ""
    assert result.sources == []


async def test_agent_memory_runtime_error_degrades_to_empty(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from fleetent import long_term_ctx

    async def _amem_unwired(*a, **k):
        raise RuntimeError("agent_memory backend not wired")

    mem = AsyncMock(return_value=[])
    know = AsyncMock(return_value=[])
    _patch_three_paths(monkeypatch, long_term_ctx, mem=mem, know=know, amem=_amem_unwired)

    # Unwired agent_memory (RuntimeError) must degrade to empty, not raise.
    result = await long_term_ctx.build_context("u1", "q", "agent-1", available_tokens=500)
    assert result.text == ""
    assert result.sources == []
