"""Unit tests: hook engine (P1) — registry + dispatch + isolation + timeout.

Pure mechanism, reset between tests; no loop/governance/platform deps.
"""

from __future__ import annotations

import asyncio

import pytest

import fleetent.runtime.hooks as hooks
from fleetent.runtime.hooks import HookContext, HookResult


@pytest.fixture(autouse=True)
def _reset():
    hooks.reset()
    yield
    hooks.reset()


def _ctx(event: str = "pre_tool_use", **payload) -> HookContext:
    return HookContext(event=event, session_id="s", agent_name="a", user_id="u", payload=payload)


async def test_register_and_dispatch_in_order():
    calls: list[str] = []

    @hooks.hook("ev")
    def a(ctx):
        calls.append("a")
        return None

    @hooks.hook("ev")
    def b(ctx):
        calls.append("b")
        return None

    assert hooks.has_hooks("ev") is True
    await hooks.dispatch("ev", _ctx("ev"))
    assert calls == ["a", "b"]


async def test_has_hooks_false_when_none():
    assert hooks.has_hooks("nope") is False


async def test_first_deny_wins_short_circuits():
    calls: list[str] = []

    @hooks.hook("pre_tool_use")
    def deny(ctx):
        calls.append("deny")
        return HookResult(decision="deny", reason="no")

    @hooks.hook("pre_tool_use")
    def never(ctx):
        calls.append("never")
        return None

    res = await hooks.dispatch("pre_tool_use", _ctx())
    assert res.decision == "deny" and res.reason == "no"
    assert calls == ["deny"]  # second hook not run


async def test_modified_args_chain():
    @hooks.hook("pre_tool_use")
    def first(ctx):
        return HookResult(modified_args={"path": "/safe/a"})

    @hooks.hook("pre_tool_use")
    def second(ctx):
        # sees the prior hook's modification chained into ctx
        assert ctx.payload["tool_args"] == {"path": "/safe/a"}
        return HookResult(modified_args={"path": "/safe/b"})

    res = await hooks.dispatch("pre_tool_use", _ctx(tool_name="write", tool_args={"path": "/x"}))
    assert res.modified_args == {"path": "/safe/b"}


async def test_exception_isolated_open():
    calls: list[str] = []

    @hooks.hook("ev")
    def boom(ctx):
        calls.append("boom")
        raise RuntimeError("kaboom")

    @hooks.hook("ev")
    def ok(ctx):
        calls.append("ok")
        return None

    res = await hooks.dispatch("ev", _ctx("ev"))  # default open
    assert calls == ["boom", "ok"]  # boom isolated, ok still runs
    assert res.decision is None  # no deny


async def test_exception_strict_denies():
    @hooks.hook("pre_tool_use")
    def boom(ctx):
        raise RuntimeError("kaboom")

    res = await hooks.dispatch("pre_tool_use", _ctx(), strict=True)
    assert res.decision == "deny"  # strict → fail-closed


async def test_timeout_skips_hook():
    @hooks.hook("ev")
    async def slow(ctx):
        await asyncio.sleep(1.0)
        return HookResult(decision="deny")

    # must not hang; slow hook times out and is skipped (open)
    res = await asyncio.wait_for(hooks.dispatch("ev", _ctx("ev"), timeout=0.02), timeout=2.0)
    assert res.decision is None  # slow deny never applied


async def test_reset_clears_registry():
    @hooks.hook("ev")
    def a(ctx):
        return None

    assert hooks.has_hooks("ev") is True
    hooks.reset()
    assert hooks.has_hooks("ev") is False


# ── config ──────────────────────────────────────────────────────────────────────


def test_governance_hooks_defaults():
    from fleetent.runtime.snapshot import GovernanceConfig

    g = GovernanceConfig()
    assert g.hooks_enabled is False
    assert g.hooks_decision_failure == "open"
    assert g.hooks_timeout_seconds == 5.0


def test_agentfile_hooks_defaults_and_mapping():
    from fleetent.agent_config import AgentFile, default_models
    from fleetent.runtime.snapshot import _governance_from_file

    a = AgentFile(name="x", version=1, models=default_models())
    assert a.hooks_enabled is False
    assert a.hooks_decision_failure == "open"
    assert a.hooks_timeout_seconds == 5.0
    g = _governance_from_file(a)
    assert g.hooks_enabled is False
    assert g.hooks_decision_failure == "open"
    assert g.hooks_timeout_seconds == 5.0

    a2 = AgentFile(
        name="y",
        version=1,
        models=default_models(),
        hooks_enabled=True,
        hooks_decision_failure="strict",
        hooks_timeout_seconds=2.0,
    )
    g2 = _governance_from_file(a2)
    assert g2.hooks_enabled is True
    assert g2.hooks_decision_failure == "strict"
    assert g2.hooks_timeout_seconds == 2.0
