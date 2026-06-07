"""Unit tests: pre_tool_use hook integration in _plan_run_slots (P1).

Drives _plan_run_slots directly with crafted tool_calls + a registered hook +
governance, asserting the decision/rewrite composition.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import fleetent.runtime.hooks as hooks
import fleetent.runtime.loop as loop
from fleetent.runtime.hooks import HookResult
from fleetent.runtime.loop_detector import LoopDetectionChecker
from fleetent.runtime.snapshot import GovernanceConfig
from fleetent.runtime.termination import LoopState


@pytest.fixture(autouse=True)
def _reset():
    hooks.reset()
    yield
    hooks.reset()


def _tc(name: str, arguments: str, tc_id: str = "tc1"):
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


async def _plan(tcs, governance, reply_func=None):
    return await loop._plan_run_slots(
        tcs,
        state=LoopState(),
        loop_checker=LoopDetectionChecker(3, []),
        guardrail_threshold=3,
        is_sub_agent=False,
        reply_func=reply_func,
        user_id="u",
        session_id=None,
        governance=governance,
        agent_name="a",
    )


async def test_pre_tool_use_deny_skips_dispatch():
    @hooks.hook("pre_tool_use")
    def block(ctx):
        if ctx.payload["tool_name"] == "danger":
            return HookResult(decision="deny", reason="blocked by policy")
        return None

    slots = await _plan([_tc("danger", '{"x":1}')], GovernanceConfig(hooks_enabled=True))
    assert slots[0].placeholder is not None  # denied → placeholder, not dispatched
    assert "blocked by policy" in slots[0].placeholder[0]
    assert slots[0].counts_failure is False


async def test_pre_tool_use_modified_args():
    @hooks.hook("pre_tool_use")
    def rewrite(ctx):
        return HookResult(modified_args={"x": 999})

    slots = await _plan([_tc("safe_tool", '{"x":1}')], GovernanceConfig(hooks_enabled=True))
    assert slots[0].placeholder is None
    assert slots[0].args == {"x": 999}  # dispatched with rewritten args


async def test_pre_tool_use_disabled_no_effect():
    @hooks.hook("pre_tool_use")
    def block(ctx):
        return HookResult(decision="deny", reason="should not run")

    slots = await _plan([_tc("safe_tool", '{"x":1}')], GovernanceConfig(hooks_enabled=False))
    assert slots[0].placeholder is None  # hooks off → no effect
    assert slots[0].args == '{"x":1}'  # original raw args, untouched


async def test_pre_tool_use_ask_forces_approval(monkeypatch):
    @hooks.hook("pre_tool_use")
    def ask(ctx):
        return HookResult(decision="ask", reason="confirm?")

    seen: dict = {}

    async def fake_req(**kw):
        seen.update(kw)
        return "approved"

    monkeypatch.setattr(loop._default_gate, "request_approval", fake_req)

    async def _reply(_s):
        return None

    slots = await _plan(
        [_tc("safe_tool", '{"x":1}')], GovernanceConfig(hooks_enabled=True), reply_func=_reply
    )
    assert seen.get("tool_name") == "safe_tool"  # ask forced approval for a low-risk tool
    assert slots[0].placeholder is None  # approved → proceeds
