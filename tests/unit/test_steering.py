"""Unit tests: run-time input steering engine (C1).

Pure asyncio + module-level registry, reset between tests. No platform, no DB.
"""

from __future__ import annotations

import pytest

import fleetent.runtime.steering as steering
from fleetent.runtime.cancellation import CancelToken


@pytest.fixture(autouse=True)
def _reset():
    steering.reset()
    yield
    steering.reset()


async def test_register_run_marks_running_then_clears():
    assert steering.is_running("s1") is False
    async with steering.register_run("s1", CancelToken()):
        assert steering.is_running("s1") is True
    assert steering.is_running("s1") is False  # handle removed on exit (no leak)


async def test_steer_enqueues_and_drains_for_active_run():
    async with steering.register_run("s1", CancelToken()):
        assert steering.steer("s1", "more A") is True
        assert steering.steer("s1", "more B") is True
        assert steering.drain("s1") == ["more A", "more B"]
        assert steering.drain("s1") == []  # cleared after drain


def test_steer_without_active_run_returns_false():
    assert steering.steer("nope", "x") is False


def test_drain_without_active_run_is_empty():
    assert steering.drain("nope") == []


async def test_steer_mailbox_cap_rejects_when_full():
    async with steering.register_run("s1", CancelToken(), max_pending=2):
        assert steering.steer("s1", "a") is True
        assert steering.steer("s1", "b") is True
        assert steering.steer("s1", "c") is False  # full → rejected (back-pressure)


async def test_interrupt_cancels_token():
    token = CancelToken()
    async with steering.register_run("s1", token):
        assert steering.interrupt("s1") is True
    assert token.is_cancelled() is True


def test_interrupt_without_active_run_returns_false():
    assert steering.interrupt("nope") is False


# ── loop-side drain ─────────────────────────────────────────────────────────────


async def test_loop_drain_steering_appends_pending():
    import fleetent.runtime.loop as loop

    msgs: list = [{"role": "system", "content": "s"}]
    async with steering.register_run("s1", CancelToken()):
        steering.steer("s1", "injected A")
        steering.steer("s1", "injected B")
        loop._drain_steering("s1", msgs)
    assert msgs[-2:] == [
        {"role": "user", "content": "injected A"},
        {"role": "user", "content": "injected B"},
    ]


def test_loop_drain_steering_noop_without_session_or_handle():
    import fleetent.runtime.loop as loop

    msgs: list = [{"role": "system", "content": "s"}]
    loop._drain_steering(None, msgs)  # no session
    loop._drain_steering("no-active-run", msgs)  # no handle
    assert msgs == [{"role": "system", "content": "s"}]  # unchanged


# ── config ──────────────────────────────────────────────────────────────────────


def test_governance_steering_defaults():
    from fleetent.runtime.snapshot import GovernanceConfig

    g = GovernanceConfig()
    assert g.steering_mode == "steer"
    assert g.steering_max_pending == 8


def test_agentfile_steering_defaults_and_mapping():
    from fleetent.agent_config import AgentFile, default_models
    from fleetent.runtime.snapshot import _governance_from_file

    a = AgentFile(name="x", version=1, models=default_models())
    assert a.steering_mode == "steer"
    assert a.steering_max_pending == 8
    g = _governance_from_file(a)
    assert g.steering_mode == "steer"
    assert g.steering_max_pending == 8

    a2 = AgentFile(
        name="y",
        version=1,
        models=default_models(),
        steering_mode="interrupt",
        steering_max_pending=3,
    )
    g2 = _governance_from_file(a2)
    assert g2.steering_mode == "interrupt"
    assert g2.steering_max_pending == 3
