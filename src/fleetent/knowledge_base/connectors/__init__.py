"""Knowledge-base connector public boundary."""

from fleetent.knowledge_base.connectors.base import DataSource, DocumentRef
from fleetent.knowledge_base.connectors.local import LocalDirectoryDataSource
from fleetent.knowledge_base.connectors.state import (
    LocalSourceState,
    LocalSourceStateStore,
)
from fleetent.knowledge_base.connectors.sync import (
    LocalDirectorySourceConfig,
    LocalSyncSummary,
    sync_local_directory,
)

__all__ = [
    "DataSource",
    "DocumentRef",
    "LocalDirectorySourceConfig",
    "LocalDirectoryDataSource",
    "LocalSourceState",
    "LocalSourceStateStore",
    "LocalSyncSummary",
    "sync_local_directory",
]
