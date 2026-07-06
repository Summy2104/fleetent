"""Declarative workflow orchestration (M1).

Agent-side DAG engine: workflow.yaml definitions → persisted runs driven to
completion with resume + governance. Public surface for triggers/wiring; the
engine instance and the enabled flag are process-scoped, injected at boot.

MUST NOT import ``fleetent.platform.*`` (agent-runtime module).
"""

from __future__ import annotations

from fleetent.workflow.definition import WorkflowDef, parse_definition
from fleetent.workflow.engine import WorkflowEngine, WorkflowInputError
from fleetent.workflow.errors import (
    WorkflowDefinitionError,
    WorkflowError,
    WorkflowMappingError,
    WorkflowNotFoundError,
)
from fleetent.workflow.loader import list_definitions, load_definition

__all__ = [
    "WorkflowDef",
    "parse_definition",
    "WorkflowEngine",
    "WorkflowInputError",
    "WorkflowError",
    "WorkflowDefinitionError",
    "WorkflowMappingError",
    "WorkflowNotFoundError",
    "load_definition",
    "list_definitions",
    "set_engine",
    "get_engine",
    "set_enabled",
    "is_enabled",
]

# Process-scoped engine + feature flag, injected at agent boot (agent_app). The tool
# availability predicate reads is_enabled(); triggers read get_engine().
_engine: WorkflowEngine | None = None
_enabled: bool = False


def set_engine(engine: WorkflowEngine | None) -> None:
    global _engine
    _engine = engine


def get_engine() -> WorkflowEngine | None:
    return _engine


def set_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = enabled


def is_enabled() -> bool:
    return _enabled
