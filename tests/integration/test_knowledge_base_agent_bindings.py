from __future__ import annotations

from dataclasses import dataclass

import pytest

from fleetent.config import KnowledgeBaseSettings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def _patch_binding_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from fleetent.knowledge_base import bindings

    db_path = tmp_path / "bindings.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(bindings, "default_database", lambda: database)
    return database


def _patch_binding_settings(monkeypatch: pytest.MonkeyPatch, default_kb_id: str = "global"):
    from fleetent.knowledge_base import bindings

    config = KnowledgeBaseSettings(default_kb_id=default_kb_id)
    monkeypatch.setattr(bindings, "_kb_config", lambda: config)
    return config


def _insert_binding(database, tenant_id: str, agent_id: str, kb_id: str) -> None:
    database.execute(
        """
        INSERT OR IGNORE INTO knowledge_base_agent_bindings (tenant_id, agent_id, kb_id, created_at)
        VALUES (:tenant_id, :agent_id, :kb_id, :created_at)
        """,
        {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "kb_id": kb_id,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )


def test_binding_public_api_is_importable():
    from fleetent.knowledge_base import (
        AgentKnowledgeBaseBinding,
        list_agent_kb_bindings,
        resolve_agent_kb_ids,
    )

    assert AgentKnowledgeBaseBinding is not None
    assert callable(list_agent_kb_bindings)
    assert callable(resolve_agent_kb_ids)


def test_agent_kb_bindings_are_tenant_and_agent_isolated(monkeypatch, tmp_path):
    database = _patch_binding_runtime(monkeypatch, tmp_path)
    _patch_binding_settings(monkeypatch)

    from fleetent.knowledge_base import list_agent_kb_bindings

    _insert_binding(database, "tenant-a", "agent-1", "engineering")
    _insert_binding(database, "tenant-b", "agent-1", "sales")
    _insert_binding(database, "tenant-a", "agent-2", "support")

    assert [binding.kb_id for binding in list_agent_kb_bindings("tenant-a", "agent-1")] == [
        "engineering"
    ]
    assert [binding.kb_id for binding in list_agent_kb_bindings("tenant-b", "agent-1")] == ["sales"]
    assert [binding.kb_id for binding in list_agent_kb_bindings("tenant-a", "agent-2")] == [
        "support"
    ]


def test_explicit_bindings_override_default_kb(monkeypatch, tmp_path):
    database = _patch_binding_runtime(monkeypatch, tmp_path)
    _patch_binding_settings(monkeypatch, default_kb_id="global")

    from fleetent.knowledge_base import resolve_agent_kb_ids

    _insert_binding(database, "tenant-a", "agent-1", "engineering")
    _insert_binding(database, "tenant-a", "agent-1", "support")

    assert resolve_agent_kb_ids("tenant-a", "agent-1") == ["engineering", "support"]


def test_missing_binding_falls_back_to_default_kb(monkeypatch, tmp_path):
    _patch_binding_runtime(monkeypatch, tmp_path)
    _patch_binding_settings(monkeypatch, default_kb_id="global")

    from fleetent.knowledge_base import resolve_agent_kb_ids

    assert resolve_agent_kb_ids("tenant-a", "agent-1") == ["global"]


def test_missing_default_kb_returns_empty_scope_and_records_diagnostic(monkeypatch, tmp_path):
    _patch_binding_runtime(monkeypatch, tmp_path)
    _patch_binding_settings(monkeypatch, default_kb_id=" ")

    from fleetent.knowledge_base import bindings, resolve_agent_kb_ids

    events = []
    monkeypatch.setattr(bindings, "record_trace_event", lambda event: events.append(event))

    assert resolve_agent_kb_ids("tenant-a", "agent-1") == []
    assert len(events) == 1
    assert events[0].event_type == "knowledge_base.agent_kb_scope_empty"
    assert events[0].tenant_id == "tenant-a"
    assert events[0].agent_id == "agent-1"
    assert events[0].payload == {
        "reason": "default_kb_missing",
        "tenant_id": "tenant-a",
        "agent_id": "agent-1",
    }


@dataclass(frozen=True)
class _KnowledgeResult:
    id: str
    content: str
    score: float
    metadata: dict[str, str]


async def test_long_term_context_searches_resolved_agent_kbs(monkeypatch):
    from fleetent import agent_config, long_term_ctx
    from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models

    agent = AgentFile(
        name="agent-1",
        version=1,
        models=default_models(),
        knowledge={
            "enabled": True,
            "bindings": [
                {"tenant_id": "tenant-a", "kb_id": "engineering"},
                {"tenant_id": "tenant-a", "kb_id": "support"},
            ],
            "retrieval_policy": {"mode": "hybrid"},
        },
    )
    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(agents={"agent-1": agent}, default="agent-1"),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search", _empty_memory_search)
    calls = []

    async def search(query: str, tenant_id: str, kb_ids: list[str], limit: int, mode: str):
        calls.append((query, tenant_id, kb_ids, limit, mode))
        return [
            _KnowledgeResult(
                id="chunk-1",
                content="Install runbook",
                score=0.8,
                metadata={"kb_id": "engineering"},
            )
        ]

    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", search)

    context = await long_term_ctx.build_context(
        user_id="user-1",
        query="what is the install process?",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert calls == [
        ("what is the install process?", "tenant-a", ["engineering", "support"], 10, "hybrid")
    ]
    assert "Install runbook" in context.text


async def test_long_term_context_skips_search_when_agent_kb_scope_is_empty(monkeypatch):
    from fleetent import agent_config, long_term_ctx
    from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models

    agent = AgentFile(
        name="agent-1",
        version=1,
        models=default_models(),
        knowledge={"enabled": False},
    )
    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(agents={"agent-1": agent}, default="agent-1"),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search", _empty_memory_search)

    async def fail_search(query: str, tenant_id: str, kb_ids: list[str], limit: int, mode: str):
        raise AssertionError("knowledge search should not be called")

    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", fail_search)

    context = await long_term_ctx.build_context(
        user_id="user-1",
        query="what is the install process?",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert context.text == ""
    assert context.sources == []


async def _empty_memory_search(
    user_id: str, query: str, limit: int, namespace: str = "default"
) -> list[object]:
    return []
