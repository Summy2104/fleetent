from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import AsyncMock

import fleetent.agent_store as agent_store
import pytest
from fleetent import agent_config, long_term_ctx
from fleetent.agent_config import AgentConfigIndex
from fleetent.knowledge_base import KnowledgeChunk
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.knowledge_base_management import agent_kbs_store
from tests.integration._migration_template import apply_migrations

_REMOVED_BINDINGS_MODULE = "fleetent.knowledge_base.bindings"
_REMOVED_SCOPE_MODULE = "fleetent.knowledge_base.retrieval.scope"
_REMOVED_TABLE = "knowledge_base_agent_bindings"
_REMOVED_RESOLVER = "resolve_agent_kb_ids("


def test_live_agent_kb_path_materializes_agent_knowledge_and_long_term_ctx_uses_it(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    agent = agent_store.create_agent("support", "You are support.", [], tenant_id="acme")
    agent_kbs_store.bind("acme", "support-kb", str(agent.id), created_by="admin")
    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))
    assert exported.knowledge.enabled is True
    assert [binding.kb_id for binding in exported.knowledge.bindings] == ["support-kb"]

    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(agents={"support": exported}, default="support"),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search", AsyncMock(return_value=[]))

    async def _search(query: str, tenant_id: str, kb_ids: list[str], limit: int, mode: str):
        assert query == "runbook"
        assert tenant_id == "acme"
        assert kb_ids == ["support-kb"]
        assert limit == 10
        assert mode == "hybrid"
        return [
            KnowledgeChunk(
                id="chunk-1",
                document_id="doc-1",
                tenant_id="acme",
                kb_id="support-kb",
                filename="guide.md",
                content="Support runbook",
                position=0,
                score=0.9,
                source="manual",
                source_url=None,
            )
        ]

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(_REMOVED_BINDINGS_MODULE)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(_REMOVED_SCOPE_MODULE)
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", _search)
    long_term_ctx.set_knowledge_provider(None)

    built = __import__("asyncio").run(
        long_term_ctx.build_context(
            user_id="user-1",
            query="runbook",
            agent_id="support",
            available_tokens=300,
        )
    )

    assert "Support runbook" in built.text


def test_dead_binding_path_has_no_src_writes_or_live_callers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    dead_table_refs: list[str] = []
    resolver_calls: list[str] = []

    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(repo_root)
        if _REMOVED_TABLE in text and any(
            keyword in text for keyword in ("INSERT INTO", "UPDATE ", "REPLACE INTO")
        ):
            dead_table_refs.append(str(rel))
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if _REMOVED_RESOLVER not in stripped:
                continue
            if stripped.startswith(f"def {_REMOVED_RESOLVER}"):
                continue
            if stripped.startswith("from ") or stripped.startswith("import "):
                continue
            resolver_calls.append(f"{rel}:{lineno}")

    assert dead_table_refs == []
    assert resolver_calls == []
