"""Supervisor for IM connector adapters: start/stop/reload driven by the registry."""

import asyncio
from collections.abc import Awaitable, Callable

from fleetent import im_connector_config, im_connector_store

# A factory is an async runner: given the resolved config dict, it runs the adapter
# until cancelled (long-lived). The adapter reports its own connected/heartbeat status.
AdapterFactory = Callable[[dict], Awaitable[None]]


class ConnectorManager:
    def __init__(self, factories: dict[str, AdapterFactory] | None = None) -> None:
        self._factories: dict[str, AdapterFactory] = factories or {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, platform: str) -> None:
        """Start a connector if it has a factory and usable config; else mark unconfigured."""
        existing = self._tasks.get(platform)
        if existing is not None and not existing.done():
            return
        factory = self._factories.get(platform)
        config = im_connector_config.resolve(platform)
        if factory is None or not config:
            im_connector_store.report_status(platform, "unconfigured")
            return
        im_connector_store.report_status(platform, "connecting")
        self._tasks[platform] = asyncio.create_task(self._run(platform, factory, config))

    async def _run(self, platform: str, factory: AdapterFactory, config: dict) -> None:
        try:
            await factory(config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # adapter crashed — reflect status, don't propagate
            im_connector_store.report_status(platform, "error", error=str(exc))

    async def stop(self, platform: str) -> None:
        task = self._tasks.pop(platform, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        im_connector_store.report_status(platform, "stopped")

    async def reload(self, platform: str) -> None:
        await self.stop(platform)
        await self.start(platform)

    def running(self) -> set[str]:
        return {p for p, t in self._tasks.items() if not t.done()}

    async def start_all_enabled(self) -> None:
        for row in im_connector_store.list_connectors():
            if row["enabled"]:
                await self.start(row["platform"])
