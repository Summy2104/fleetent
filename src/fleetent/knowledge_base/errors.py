from __future__ import annotations


class KnowledgeBaseEmbeddingMismatchError(RuntimeError):
    """Raised when the active embedding identity does not match a KB's stamped identity."""


def embedding_mismatch_message(
    *,
    tenant_id: str,
    kb_id: str,
    expected_model: str,
    expected_dimensions: int,
    current_model: str,
    current_dimensions: int,
    operation: str,
) -> str:
    return (
        f"Knowledge base embedding mismatch for {tenant_id}/{kb_id}: "
        f"KB uses model={expected_model} dimensions={expected_dimensions}, "
        f"current {operation} uses model={current_model} dimensions={current_dimensions}"
    )
