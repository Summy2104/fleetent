"""Per-agent Slack IM binding supervisor (per-agent-slack-connector).

Sources the agent index (`agent_config`) and runs one Slack Socket Mode connection per
agent that declares `im.slack` with resolvable env tokens. Keyed by agent name;
owns per-agent connection status. Replaces the owner-level connector manager for Slack.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from fleetent import agent_config
from fleetent.agent_config import SlackBinding
from fleetent.im_gateway import slack
from fleetent.structured_logging import get_logger

_logger = get_logger("im_gateway.slack")

# Runner signature: (agent_name, config) -> runs until cancelled.
Runner = Callable[[str, dict[str, Any]], Awaitable[None]]


class SlackSupervisor:
    def __init__(
        self,
        runner: Runner | None = None,
    ) -> None:
        # When no runner is injected, slack.run is resolved at call time so it can be
        # monkeypatched (the module-level supervisor is built at import).
        self._runner: Runner | None = runner
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._status: dict[str, str] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    def _resolve_config(self, binding: SlackBinding) -> dict[str, Any] | None:
        bot = os.environ.get(binding.bot_token_env)
        app = os.environ.get(binding.app_token_env)
        if not bot or not app:
            return None
        return {"bot_token": bot, "app_token": app}

    async def start(self, agent_name: str) -> None:
        agent = agent_config.current().get(agent_name)
        if agent is None or agent.im.slack is None:
            return
        config = self._resolve_config(agent.im.slack)
        if config is None:
            self._status[agent_name] = "unconfigured"
            _logger.warn("slack_connector_unconfigured", agent=agent_name)
            return
        existing = self._tasks.get(agent_name)
        if existing is not None and not existing.done():
            return
        self._status[agent_name] = "connecting"
        self._configs[agent_name] = config
        self._tasks[agent_name] = asyncio.create_task(self._run(agent_name, config))

    async def _run(self, agent_name: str, config: dict[str, Any]) -> None:
        self._status[agent_name] = "connected"
        runner = self._runner or slack.run
        try:
            await runner(agent_name, config)
        except asyncio.CancelledError:
            self._status[agent_name] = "stopped"
            raise
        except Exception as exc:  # connection crashed — reflect status, isolate failure
            self._status[agent_name] = "error"
            _logger.warn("slack_connector_error", agent=agent_name, error=str(exc))

    async def stop(self, agent_name: str) -> None:
        task = self._tasks.pop(agent_name, None)
        self._configs.pop(agent_name, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._status[agent_name] = "stopped"

    async def start_from_index(self) -> None:
        for name in agent_config.current().slack_agents():
            await self.start(name)

    async def reload(self) -> None:
        """Reconcile running connections against the current index: add/remove/restart."""
        declared = set(agent_config.current().slack_agents())
        for name in self.running() - declared:
            await self.stop(name)
        for name in declared:
            agent = agent_config.current().get(name)
            assert agent is not None and agent.im.slack is not None
            new_config = self._resolve_config(agent.im.slack)
            running = name in self._tasks and not self._tasks[name].done()
            if running and new_config != self._configs.get(name):
                await self.stop(name)  # config changed → restart
            await self.start(name)

    async def stop_all(self) -> None:
        for name in list(self._tasks):
            await self.stop(name)

    def running(self) -> set[str]:
        return {name for name, t in self._tasks.items() if not t.done()}

    def status(self) -> dict[str, str]:
        return dict(self._status)
