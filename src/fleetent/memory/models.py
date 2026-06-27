"""Structured per-agent semantic memory models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AgentMemoryType = Literal["context", "preference", "procedure"]
AgentMemoryStatus = Literal["active", "stale", "archived"]
AgentMemorySource = Literal["manual", "reflection_proposal"]


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
