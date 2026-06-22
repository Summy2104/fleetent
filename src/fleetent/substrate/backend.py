"""Pluggable substrate backend abstraction for agent-side relational stores."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, ClassVar

Params = Mapping[str, object]


@dataclass(frozen=True)
class SubstrateCapabilities:
    """Optional substrate behaviours that callers gate on by capability."""

    network: bool
    shared_across_hosts: bool
    embedded_migrations: bool


class BaseSubstrateBackend(ABC):
    """Abstract relational substrate backend."""

    dialect: ClassVar[str]
    capabilities: ClassVar[SubstrateCapabilities]

    @abstractmethod
    def execute(self, sql: str, params: Params | None = None) -> Any:
        """Execute one statement and return a backend-specific result."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager[Any]:
        """Return a transaction context manager."""

    @abstractmethod
    def local_path(self) -> str | None:
        """Return the local filesystem path when the backend is file-backed."""
