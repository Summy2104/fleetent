from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx

from fleetent import agent_config, long_term_ctx
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.identity import INGRESS_PRINCIPAL_HEADER, Principal, encode_ingress_principal
from fleetent.knowledge_base import KnowledgeChunk
from fleetent.memory.facts_models import Fact, SearchResult


def _chunk() -> KnowledgeChunk:
    return KnowledgeChunk(
        id="chunk-1",
        document_id="doc-1",
        tenant_id="tenant-a",
        kb_id="kb-1",
        filename="guide.md",
        content="Fleetent supports on-prem knowledge retrieval.",
        position=3,
        score=0.91,
        source="manual",
        source_url="https://kb.example/doc-1",
        metadata={"section": "deploy", "lang": "en"},
    )


async def test_http_knowledge_provider_posts_wire_payload_and_parses_chunks() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["principal_header"] = request.headers[INGRESS_PRINCIPAL_HEADER]
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"chunks": [long_term_ctx._knowledge_chunk_to_wire_dict(_chunk())]},
            request=request,
        )

    provider = long_term_ctx.HttpKnowledgeProvider(
        "https://kb.example/search",
        service_key="svc-secret",
        transport=httpx.MockTransport(handler),
    )

    results = await provider(
        Principal(user_id="user-1", tenant_id="tenant-a"),
        "deployment",
        ["kb-1", "kb-2"],
        7,
        None,
    )

    assert captured == {
        "method": "POST",
        "url": "https://kb.example/search",
        "authorization": "Bearer svc-secret",
        "principal_header": encode_ingress_principal(
            Principal(user_id="user-1", tenant_id="tenant-a")
        ),
        "json": {
            "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
            "query": "deployment",
            "kb_ids": ["kb-1", "kb-2"],
            "limit": 7,
        },
    }
    assert results == [_chunk()]


def _publish_agent(monkeypatch, agent: AgentFile) -> None:
    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(agents={agent.name: agent}, default=agent.name),
    )


def _memory_result() -> SearchResult:
    now = datetime.now(UTC)
    return SearchResult(
        fact=Fact(
            fact_id="mem-1",
            user_id="user-1",
            subject="user",
            relation="preference",
            object="concise answers",
            cardinality="multi",
            status="active",
            access_count=0,
            first_accessed_at=None,
            last_accessed_at=None,
            expires_at=None,
            valid_until=None,
            created_at=now,
            updated_at=now,
            source_turn=None,
            statement="User prefers concise answers.",
        ),
        score=0.9,
    )


class _FakeLogger:
    def __init__(self) -> None:
        self.warns: list[tuple[str, dict[str, object]]] = []

    def warn(self, message: str, **fields: object) -> None:
        self.warns.append((message, dict(fields)))

    def info(self, _message: str, **_fields: object) -> None:
        return None


async def test_http_knowledge_provider_degrades_to_empty_on_http_errors(monkeypatch) -> None:
    logger = _FakeLogger()
    monkeypatch.setattr(long_term_ctx, "_logger", logger)

    cases = [
        (
            "status",
            httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
            "HTTPStatusError",
        ),
        (
            "connect",
            httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("down"))),
            "ConnectError",
        ),
        (
            "timeout",
            httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request))
            ),
            "ReadTimeout",
        ),
    ]

    for name, transport, error_type in cases:
        provider = long_term_ctx.HttpKnowledgeProvider(
            "https://kb.example/search",
            service_key="svc-secret",
            transport=transport,
        )
        results = await provider(
            Principal(user_id="user-1", tenant_id="tenant-a"),
            "deployment",
            ["kb-1"],
            5,
            None,
        )

        assert results == [], name
        assert logger.warns[-1][0] == "http_knowledge_provider_failed"
        assert logger.warns[-1][1]["error_type"] == error_type


async def test_build_context_keeps_memory_and_always_facts_when_http_provider_degrades(
    monkeypatch,
) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(return_value=[_memory_result()]),
    )
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        long_term_ctx,
        "_list_always_facts",
        lambda _user_id: [
            type(
                "AlwaysFact",
                (),
                {
                    "fact_id": "always-1",
                    "statement": "Always verify tenant boundaries.",
                    "subject": "agent",
                    "relation": "directive",
                    "object": "verify tenant boundaries",
                },
            )()
        ],
    )
    long_term_ctx.set_knowledge_provider(
        long_term_ctx.HttpKnowledgeProvider(
            "https://kb.example/search",
            service_key="svc-secret",
            transport=httpx.MockTransport(boom),
        )
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="deployment",
        agent_id="agent-1",
        available_tokens=300,
    )

    assert "Always verify tenant boundaries." in result.text
    assert "User prefers concise answers." in result.text
    assert "[Knowledge" not in result.text
    assert [source.source_type for source in result.sources] == ["memory", "memory"]


async def test_build_context_forwards_materialized_kb_ids_to_knowledge_provider(
    monkeypatch,
) -> None:
    seen: dict[str, object] = {}

    async def provider(principal, query, kb_ids, limit, audit_context):
        seen["principal"] = principal
        seen["query"] = query
        seen["kb_ids"] = list(kb_ids)
        seen["limit"] = limit
        seen["audit_context"] = audit_context
        return []

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [
                    {"tenant_id": "tenant-a", "kb_id": "kb-1"},
                    {"tenant_id": "tenant-a", "kb_id": "kb-2"},
                ],
            },
        ),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        long_term_ctx.agent_memory, "search_agent_memory", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(long_term_ctx, "_list_always_facts", lambda _user_id: [])
    long_term_ctx.set_knowledge_provider(provider)

    await long_term_ctx.build_context(
        user_id="user-1",
        query="deployment",
        agent_id="agent-1",
        available_tokens=300,
    )

    assert seen["query"] == "deployment"
    assert seen["kb_ids"] == ["kb-1", "kb-2"]
