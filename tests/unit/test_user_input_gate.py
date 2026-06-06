"""Tests for user_input_gate (builtin-interaction-tools spec)."""

from __future__ import annotations

import asyncio

import pytest

from fleetent.governance.user_input_gate import UserInputGate, answer, wait_for_answer


async def test_answer_resolves_wait():
    gate = UserInputGate()
    session = "s1"

    async def _reply():
        await asyncio.sleep(0.05)
        gate.answer(session, "yes")

    asyncio.create_task(_reply())
    result = await gate.wait(session, timeout=2.0)
    assert result == "yes"


async def test_wait_timeout_returns_timeout_string():
    gate = UserInputGate()
    result = await gate.wait("session_x", timeout=0.05)
    assert "timeout" in result.lower() or "超时" in result


async def test_session_isolation():
    gate = UserInputGate()
    gate.answer("s1", "for_s1")
    # s2 should not receive s1's answer
    result = await gate.wait("s2", timeout=0.05)
    assert "timeout" in result.lower() or "超时" in result


async def test_answer_after_wait_resolves():
    gate = UserInputGate()

    async def _late_answer():
        await asyncio.sleep(0.02)
        gate.answer("late_sess", "ok")

    asyncio.create_task(_late_answer())
    result = await gate.wait("late_sess", timeout=1.0)
    assert result == "ok"


async def test_cleanup_removes_session_entry():
    gate = UserInputGate()
    gate.answer("temp", "done")
    await gate.wait("temp", timeout=1.0)
    gate.cleanup("temp")
    # After cleanup, waiting again should timeout (no pending answer)
    result = await gate.wait("temp", timeout=0.05)
    assert "timeout" in result.lower() or "超时" in result


async def test_module_level_functions_use_shared_gate():
    session = "global_s"
    answer(session, "42")
    result = await wait_for_answer(session, timeout=1.0)
    assert result == "42"
