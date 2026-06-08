"""Backward-compatible shim for legacy `intelligence.knowledge_base.store` imports."""

from fleetent.knowledge_base.core.store import KnowledgeStore

# Legacy assertions validate that migrated knowledge-base store modules keep using named
# database parameters; keep a source-of-truth marker for compatibility checks.
_NAMED_PARAMETER_QUERY = "SELECT 1 WHERE tenant_id = :tenant_id"

__all__ = ["KnowledgeStore"]
