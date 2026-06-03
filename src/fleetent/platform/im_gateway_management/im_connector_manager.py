"""Supervisor for IM connector adapters: start/stop/reload driven by the registry."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fleetent.platform.im_gateway_management import im_connector_config, im_connector_store

# A factory is an async runner: given the owner id and resolved config, it runs the
# adapter until cancelled (long-lived). The adapter reports its own connected/heartbeat
# status and stamps owner_id onto inbound messages.
AdapterFactory = Callable[[str, dict[str, str]], Awaitable[None]]

# Tasks are keyed by (owner_id, platform) so multiple owners can run the same platform.
_Key = tuple[str, str]


class ConnectorManager:
    def __init__(self, factories: dict[str, AdapterFactory] | None = None) -> None:
        self._factories: dict[str, AdapterFactory] = factories or {}
        self._tasks: dict[_Key, asyncio.Task[Any]] = {}

    async def start(self, owner_id: str, platform: str) -> None:
        """Start a connector if it has a factory and usable config; else mark unconfigured."""
        key = (owner_id, platform)
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            return
        factory = self._factories.get(platform)
        config = im_connector_config.resolve(owner_id, platform)
        if factory is None or not config:
            im_connector_store.report_status(owner_id, platform, "unconfigured")
            return
        im_connector_store.report_status(owner_id, platform, "connecting")
        self._tasks[key] = asyncio.create_task(self._run(owner_id, platform, factory, config))

    async def _run(
        self, owner_id: str, platform: str, factory: AdapterFactory, config: dict[str, str]
    ) -> None:
        try:
            await factory(owner_id, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # adapter crashed — reflect status, don't propagate
            im_connector_store.report_status(owner_id, platform, "error", error=str(exc))

    async def stop(self, owner_id: str, platform: str) -> None:
        task = self._tasks.pop((owner_id, platform), None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        im_connector_store.report_status(owner_id, platform, "stopped")

    async def reload(self, owner_id: str, platform: str) -> None:
        await self.stop(owner_id, platform)
        await self.start(owner_id, platform)

    def running(self) -> set[_Key]:
        return {key for key, t in self._tasks.items() if not t.done()}

    async def start_all_enabled(self) -> None:
        for row in im_connector_store.list_connectors():
            if row["enabled"]:
                await self.start(row["owner_id"], row["platform"])
