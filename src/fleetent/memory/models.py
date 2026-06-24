"""Structured per-user semantic memory models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

MemoryType = Literal["identity", "preferences", "context"]
AgentMemoryType = Literal["context", "preference", "procedure"]
AgentMemoryStatus = Literal["active", "stale", "archived"]
AgentMemorySource = Literal["manual", "reflection_proposal"]


@dataclass(frozen=True)
class MemoryItem:
    """A structured semantic memory item."""

    id: str
    user_id: str
    type: MemoryType
    content: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True)
class AgentMemoryItem:
    """A confirmed agent-scoped semantic memory item.

    Isolation is per-agent physical DB — no scope columns needed.
    """

    id: str
    type: AgentMemoryType
    content: str
    status: AgentMemoryStatus
    source: AgentMemorySource
    source_ref: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MemoryMaintenancePolicy:
    """Per-user semantic memory retention and compaction limits."""

    max_identity: int = 20
    max_preferences: int = 30
    max_context: int = 20
    compact_duplicates: bool = True


@dataclass(frozen=True)
class MemoryCompactionCandidate:
    """Duplicate memory group that can be compacted deterministically."""

    type: MemoryType
    canonical_id: str
    duplicate_ids: list[str]
    reason: str


@dataclass(frozen=True)
class MemoryMaintenanceSummary:
    """Summary returned by one memory maintenance run."""

    user_id: str
    dry_run: bool
    expired_count: int
    over_limit_count: int
    compacted_count: int
    deleted_ids: list[str]
    compaction_candidates: list[MemoryCompactionCandidate]
