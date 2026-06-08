"""Sync connectors exposed from the legacy knowledge_base location."""

from fleetent.knowledge_base.connectors.sync import (  # noqa: F401
    LocalDirectorySourceConfig,
    LocalSyncSummary,
    sync_local_directory,
)

__all__ = [
    "LocalDirectorySourceConfig",
    "LocalSyncSummary",
    "sync_local_directory",
]
