"""Compatibility layer for ingest connectors."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sync import LocalDirectorySourceConfig, LocalSyncSummary, sync_local_directory


def __getattr__(name: str) -> object:
    if name == "sync":
        return import_module("fleetent.knowledge_base.ingest.connectors.sync")
    if name in {"LocalDirectorySourceConfig", "LocalSyncSummary", "sync_local_directory"}:
        from .sync import LocalDirectorySourceConfig, LocalSyncSummary, sync_local_directory

        return {
            "LocalDirectorySourceConfig": LocalDirectorySourceConfig,
            "LocalSyncSummary": LocalSyncSummary,
            "sync_local_directory": sync_local_directory,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        [
            *globals(),
            "sync",
            "LocalDirectorySourceConfig",
            "LocalSyncSummary",
            "sync_local_directory",
        ]
    )


__all__ = [
    "sync",
    "LocalDirectorySourceConfig",
    "LocalSyncSummary",
    "sync_local_directory",
]
