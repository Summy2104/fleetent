"""Re-export shim — protocols moved to knowledge_base.core.protocols (canonical location)."""

from fleetent.knowledge_base.core.models import (  # noqa: F401
    KnowledgeChunk,
    KnowledgeDocument,
)
from fleetent.knowledge_base.core.protocols import (  # noqa: F401
    KnowledgeReadable,
    KnowledgeWritable,
)

__all__ = [
    "KnowledgeReadable",
    "KnowledgeWritable",
    "KnowledgeChunk",
    "KnowledgeDocument",
]
