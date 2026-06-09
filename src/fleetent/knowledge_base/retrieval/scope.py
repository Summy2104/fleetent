from fleetent.config import KnowledgeBaseSettings

# Re-export from the single source of truth for agent-KB binding reads.
from fleetent.knowledge_base.bindings import (
    AgentKnowledgeBaseBinding,
    resolve_agent_kb_ids,
)

__all__ = ["AgentKnowledgeBaseBinding", "resolve_agent_kb_ids"]


def _kb_config() -> KnowledgeBaseSettings:
    return KnowledgeBaseSettings()
