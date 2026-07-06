"""Shared workflow error types.

Kept in a dependency-free module so ``definition``, ``mapping``, ``store``,
``steps`` and ``engine`` can raise/catch a common hierarchy without importing
each other.
"""

from __future__ import annotations


class WorkflowError(Exception):
    """Base class for all workflow-layer errors."""


class WorkflowDefinitionError(WorkflowError):
    """A workflow.yaml is structurally invalid or fails load-time validation."""


class WorkflowMappingError(WorkflowError):
    """A ``${...}`` reference cannot be resolved at runtime (fail-closed)."""


class WorkflowNotFoundError(WorkflowError):
    """No workflow definition exists for the requested name."""
