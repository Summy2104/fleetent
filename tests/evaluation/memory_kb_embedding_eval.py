import asyncio
import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from fleetent.agent_config import (
    AgentFile,
    AgentModels,
    ModelRouteEntry,
    ModelTarget,
    default_models,
)
from fleetent.config import EmbeddingSettings, KnowledgeBaseSettings, Settings, VectorStoreSettings
from fleetent.db import create_database
from fleetent.vector_store import ReindexSummary
from tests.integration.test_migrations import apply_migrations

REQUIRED_FIXTURE_FIELDS = (
    "name",
    "user_id",
    "tenant_id",
    "kb_id",
    "memories",
    "documents",
    "queries",
)
_QUERY_OWNERS = {"memory", "knowledge_base"}
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "memory_kb_embedding"


class FixtureValidationError(ValueError):
    """Raised when a combined memory/KB embedding evaluation fixture is invalid."""


@dataclass(frozen=True)
class CombinedEmbeddingEvaluationResult:
    """Result captured from a combined memory/KB embedding evaluation run."""

    db_path: Path
    vector_db_path: Path
    memory_reindex_summary: ReindexSummary
    kb_reindex_summary: ReindexSummary
    query_results: list["CombinedQueryResult"]


@dataclass(frozen=True)
class CombinedQueryResult:
    """Retrieved text and expectations captured for one memory or KB query."""

    owner: str
    query: str
    texts: list[str]
    expected: list[str]
    forbidden: list[str]


def validate_fixture(fixture: Mapping[str, Any]) -> None:
    """Validate the combined memory/KB embedding evaluation fixture schema."""
    missing = [field for field in REQUIRED_FIXTURE_FIELDS if field not in fixture]
    if missing:
        raise FixtureValidationError(f"missing required fixture fields: {', '.join(missing)}")

    _require_non_empty_string(fixture["name"], "name")
    _require_non_empty_string(fixture["user_id"], "user_id")
    _require_non_empty_string(fixture["tenant_id"], "tenant_id")
    _require_non_empty_string(fixture["kb_id"], "kb_id")
    _require_sequence(fixture["memories"], "memories")
    _require_sequence(fixture["documents"], "documents")
    _require_sequence(fixture["queries"], "queries")

    for index, query in enumerate(fixture["queries"]):
        if not isinstance(query, Mapping):
            raise FixtureValidationError(f"queries[{index}] must be an object")
        owner = query.get("owner")
        if owner not in _QUERY_OWNERS:
            raise FixtureValidationError(f"queries[{index}].owner is invalid: {owner}")
        _require_non_empty_string(query.get("text"), f"queries[{index}].text")
        top_k = query.get("top_k")
        if not isinstance(top_k, int) or top_k <= 0:
            raise FixtureValidationError(f"queries[{index}].top_k must be a positive integer")
        _require_sequence(query.get("expected"), f"queries[{index}].expected")
        _require_sequence(query.get("forbidden"), f"queries[{index}].forbidden")
        _require_string_items(query["expected"], f"queries[{index}].expected")
        _require_string_items(query["forbidden"], f"queries[{index}].forbidden")


def load_fixtures(fixture_dir: Path = _FIXTURE_DIR) -> list[dict[str, Any]]:
    """Load and validate combined memory/KB embedding evaluation fixtures."""
    fixtures: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        fixture = json.loads(path.read_text())
        if not isinstance(fixture, dict):
            raise FixtureValidationError(f"{path.name} must contain a fixture object")
        validate_fixture(fixture)
        fixtures.append(fixture)
    return fixtures


async def run_deterministic_fixture(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any
) -> CombinedEmbeddingEvaluationResult:
    """Run one fixture with deterministic embedding and isolated SQLite databases."""
    validate_fixture(fixture)
    db_path = tmp_path / "memory-kb-embedding-eval.db"
    vector_db_path = tmp_path / "memory-kb-embedding-vectors.db"
    return await _run_fixture(
        fixture,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        db_path=db_path,
        vector_db_path=vector_db_path,
        embedding=EmbeddingSettings(backend="deterministic", dimensions=64),
    )


async def run_real_embedding_fixture(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any
) -> CombinedEmbeddingEvaluationResult:
    """Run one fixture with a real HTTP embedding provider when explicitly enabled."""
    if os.environ.get("FLEETENT_EVAL_REAL_EMBEDDING") != "1":
        pytest.skip("set FLEETENT_EVAL_REAL_EMBEDDING=1 to run real embedding evaluation")

    endpoint = os.environ.get("FLEETENT_EVAL_EMBEDDING_ENDPOINT", "")
    model = os.environ.get("FLEETENT_EVAL_EMBEDDING_MODEL", "")
    api_key = os.environ.get("FLEETENT_EVAL_EMBEDDING_API_KEY", "")
    raw_dimensions = os.environ.get("FLEETENT_EVAL_EMBEDDING_DIMENSIONS", "")
    if not endpoint or not model or not api_key or not raw_dimensions:
        pytest.skip("real embedding evaluation requires endpoint, model, API key, and dimensions")

    db_path = tmp_path / "memory-kb-embedding-real-eval.db"
    vector_db_path = tmp_path / "memory-kb-embedding-real-vectors.db"
    return await _run_fixture(
        fixture,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        db_path=db_path,
        vector_db_path=vector_db_path,
        embedding=EmbeddingSettings(
            backend="http",
            dimensions=int(raw_dimensions),
            endpoint=endpoint,
            model=model,
            api_key_env="FLEETENT_EVAL_EMBEDDING_API_KEY",
        ),
    )


async def _run_fixture(
    fixture: Mapping[str, Any],
    *,
    tmp_path: Path,
    monkeypatch: Any,
    db_path: Path,
    vector_db_path: Path,
    embedding: EmbeddingSettings,
) -> CombinedEmbeddingEvaluationResult:
    from fleetent import agent_config
    from fleetent.intelligence import knowledge_base, vector_store
    from fleetent.intelligence.knowledge_base import runtime as kb_runtime
    from fleetent.vector_store import runtime as vector_runtime

    apply_migrations(db_path)
    database_url = f"sqlite:///{db_path}"
    kb_settings = KnowledgeBaseSettings(
        enabled=True,
        chunk_size=120,
        chunk_overlap=0,
    )
    agent = _agent_for_embedding(
        embedding,
        vector_store=VectorStoreSettings(
            backend="sqlite",
            database_url=f"sqlite:///{vector_db_path}",
        ),
    )
    settings = Settings(database_url=database_url)
    database = create_database(database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(agent_config, "active_agent_or_default", lambda: agent)
    monkeypatch.setattr(kb_runtime, "_settings", lambda: settings)
    monkeypatch.setattr(kb_runtime, "_database", lambda: database)
    monkeypatch.setattr(kb_runtime, "_kb_config", lambda: kb_settings)
    vector_runtime._configure(agent)

    try:
        _insert_memories(db_path, str(fixture["user_id"]), fixture["memories"])
        for document in fixture["documents"]:
            await knowledge_base.ingest_text(
                filename=str(document["filename"]),
                content=str(document["content"]),
                tenant_id=str(fixture["tenant_id"]),
                kb_id=str(fixture["kb_id"]),
                source=str(document.get("source", "evaluation")),
                source_url=document.get("source_url"),
            )

        memory_summary = await asyncio.to_thread(
            vector_store.reindex,
            vector_store.ReindexRequest(owner="memory", user_id=str(fixture["user_id"])),
        )
        kb_summary = await asyncio.to_thread(
            vector_store.reindex,
            vector_store.ReindexRequest(
                owner="knowledge_base",
                tenant_id=str(fixture["tenant_id"]),
                kb_id=str(fixture["kb_id"]),
            ),
        )
        query_results = await _run_queries(fixture)
        return CombinedEmbeddingEvaluationResult(
            db_path=db_path,
            vector_db_path=vector_db_path,
            memory_reindex_summary=memory_summary,
            kb_reindex_summary=kb_summary,
            query_results=query_results,
        )
    finally:
        vector_runtime._configure(AgentFile(name="", version=0, models=default_models()))


def _agent_for_embedding(
    embedding: EmbeddingSettings,
    *,
    vector_store: VectorStoreSettings,
) -> AgentFile:
    if embedding.backend == "deterministic":
        return AgentFile(
            name="",
            version=0,
            models=default_models(),
            vector_store=vector_store,
        )
    if embedding.backend == "http":
        return AgentFile(
            name="memory-kb-real-embedding-eval",
            version=1,
            models=AgentModels(
                targets=[
                    ModelTarget(
                        id="embedding",
                        provider="evaluation",
                        protocol="http_embedding",
                        endpoint=embedding.endpoint,
                        model=embedding.model,
                        api_key_env=embedding.api_key_env,
                        params={"dimensions": embedding.dimensions},
                    )
                ],
                routes={"embedding": [ModelRouteEntry(target="embedding")]},
            ),
            vector_store=vector_store,
        )
    raise FixtureValidationError(f"unsupported embedding backend: {embedding.backend}")


def assert_query_expectations(result: CombinedEmbeddingEvaluationResult) -> None:
    """Assert every query result satisfies expected and forbidden snippet assertions."""
    for query_result in result.query_results:
        for expected in query_result.expected:
            if not _contains_snippet(query_result.texts, expected):
                raise AssertionError(f"expected {query_result.owner} snippet not found: {expected}")
        for forbidden in query_result.forbidden:
            if _contains_snippet(query_result.texts, forbidden):
                raise AssertionError(f"forbidden {query_result.owner} snippet found: {forbidden}")


def _require_non_empty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FixtureValidationError(f"{field} must be a non-empty string")


def _require_sequence(value: object, field: str) -> None:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise FixtureValidationError(f"{field} must be a sequence")


def _require_string_items(value: object, field: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise FixtureValidationError(f"{field} must be a sequence")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise FixtureValidationError(f"{field}[{index}] must be a string")


def _insert_memories(db_path: Path, user_id: str, memories: object) -> None:
    if not isinstance(memories, Sequence) or isinstance(memories, str):
        raise FixtureValidationError("memories must be a sequence")
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    with sqlite3.connect(db_path) as conn:
        for index, memory in enumerate(memories):
            if not isinstance(memory, Mapping):
                raise FixtureValidationError(f"memories[{index}] must be an object")
            conn.execute(
                """
                INSERT INTO memory_items (
                    id, user_id, type, content, created_at, updated_at, expires_at
                )
                VALUES (
                    :id, :user_id, :type, :content, :created_at, :updated_at, :expires_at
                )
                """,
                {
                    "id": str(memory["id"]),
                    "user_id": user_id,
                    "type": str(memory["type"]),
                    "content": str(memory["content"]),
                    "created_at": now,
                    "updated_at": now,
                    "expires_at": memory.get("expires_at"),
                },
            )


async def _run_queries(fixture: Mapping[str, Any]) -> list[CombinedQueryResult]:
    from fleetent.intelligence import knowledge_base
    from fleetent.intelligence import memory as memory_layer

    results: list[CombinedQueryResult] = []
    for query in fixture["queries"]:
        if query["owner"] == "memory":
            memories = await memory_layer.search(
                str(fixture["user_id"]), str(query["text"]), limit=int(query["top_k"])
            )
            texts = [memory.content for memory in memories]
        else:
            chunks = await knowledge_base.search(
                str(query["text"]),
                tenant_id=str(fixture["tenant_id"]),
                kb_ids=[str(fixture["kb_id"])],
                limit=int(query["top_k"]),
            )
            texts = [chunk.content for chunk in chunks]
        results.append(
            CombinedQueryResult(
                owner=str(query["owner"]),
                query=str(query["text"]),
                texts=texts,
                expected=list(query["expected"]),
                forbidden=list(query["forbidden"]),
            )
        )
    return results


def _contains_snippet(contents: Sequence[str], snippet: str) -> bool:
    normalized = snippet.casefold()
    return any(normalized in content.casefold() for content in contents)
