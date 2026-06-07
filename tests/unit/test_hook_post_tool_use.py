"""Unit tests: post_tool_use hook integration in _backfill_slots (P2).

Drives _backfill_slots directly with crafted slots + registered hook + governance,
asserting the modified_content / observation / placeholder-skip semantics.
"""

from __future__ import annotations

import pytest

import fleetent.runtime.hooks as hooks
import fleetent.runtime.loop as loop
from fleetent.runtime.hooks import HookResult
from fleetent.runtime.loop import _PlanSlot
from fleetent.runtime.loop_detector import LoopDetectionChecker
from fleetent.runtime.snapshot import GovernanceConfig
from fleetent.runtime.termination import LoopState


@pytest.fixture(autouse=True)
def _reset():
    hooks.reset()
    yield
    hooks.reset()


def _slot(name: str, args: str | dict, tc_id: str = "tc1") -> _PlanSlot:
    return _PlanSlot(tc_id=tc_id, name=name, tc_fp="fp", args=args)


def _placeholder(name: str, content: str, tc_id: str = "tc1") -> _PlanSlot:
    return _PlanSlot(tc_id=tc_id, name=name, tc_fp="fp", placeholder=(content, False))


async def _backfill(
    slots: list[_PlanSlot],
    results: dict[str, tuple[str, bool]],
    governance: GovernanceConfig,
) -> list[dict]:
    messages: list = []
    await loop._backfill_slots(
        slots,
        results,
        messages=messages,
        state=LoopState(),
        loop_checker=LoopDetectionChecker(3, []),
        governance=governance,
        session_id=None,
        agent_name="a",
        user_id="u",
    )
    return messages


async def test_post_tool_use_modified_content_replaces_result():
    @hooks.hook("post_tool_use")
    def redact(ctx):
        if ctx.payload["tool_name"] == "secret_tool":
            return HookResult(modified_content="[REDACTED]")
        return None

    messages = await _backfill(
        [_slot("secret_tool", '{"x":1}')],
        {"tc1": ("sensitive data", False)},
        GovernanceConfig(hooks_enabled=True),
    )
    assert messages[0]["content"] == "[REDACTED]"


async def test_post_tool_use_none_keeps_original():
    @hooks.hook("post_tool_use")
    def observe(ctx):
        return None

    messages = await _backfill(
        [_slot("safe_tool", '{"x":1}')],
        {"tc1": ("original result", False)},
        GovernanceConfig(hooks_enabled=True),
    )
    assert "original result" in messages[0]["content"]


async def test_post_tool_use_placeholder_not_triggered():
    called: list[str] = []

    @hooks.hook("post_tool_use")
    def track(ctx):
        called.append(ctx.payload["tool_name"])
        return None

    messages = await _backfill(
        [_placeholder("denied_tool", "tool execution denied by policy")],
        {},
        GovernanceConfig(hooks_enabled=True),
    )
    assert called == []
    assert "denied" in messages[0]["content"]


async def test_post_tool_use_disabled_no_effect():
    @hooks.hook("post_tool_use")
    def redact(ctx):
        return HookResult(modified_content="[REDACTED]")

    messages = await _backfill(
        [_slot("secret_tool", '{"x":1}')],
        {"tc1": ("original result", False)},
        GovernanceConfig(hooks_enabled=False),
    )
    assert "original result" in messages[0]["content"]
