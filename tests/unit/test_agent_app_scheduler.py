"""_start_scheduler wires the agent's CronScheduler at boot (agent-owned-scheduled-tasks).

CronScheduler is mocked (no DB / APScheduler), keeping this at unit level.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import fleetent.im_gateway.connector_registry as reg
from fleetent.runtime import agent_app


def _agent(enabled: bool = True, name: str = "bot-a") -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.scheduling.enabled = enabled
    return agent


async def test_start_scheduler_returns_none_when_disabled() -> None:
    with patch("fleetent.cron_scheduler.CronScheduler") as cls:
        result = await agent_app._start_scheduler(_agent(enabled=False))
    assert result is None
    cls.assert_not_called()


async def test_start_scheduler_starts_and_returns_scheduler_when_enabled() -> None:
    instance = MagicMock()
    instance.start = AsyncMock()
    with patch("fleetent.cron_scheduler.CronScheduler", return_value=instance) as cls:
        result = await agent_app._start_scheduler(_agent(enabled=True))

    assert result is instance
    instance.start.assert_awaited_once()
    cls.assert_called_once()


async def test_start_scheduler_resolver_reads_connector_registry() -> None:
    captured = {}

    def _fake_ctor(settings=None, connectors_resolver=None):  # type: ignore[no-untyped-def]
        captured["resolver"] = connectors_resolver
        inst = MagicMock()
        inst.start = AsyncMock()
        return inst

    with patch("fleetent.cron_scheduler.CronScheduler", side_effect=_fake_ctor):
        await agent_app._start_scheduler(_agent(enabled=True, name="bot-a"))

    reg._clear()
    conn = object()
    reg.register("slack", "bot-a", conn)
    assert captured["resolver"]() == {"slack": conn}
