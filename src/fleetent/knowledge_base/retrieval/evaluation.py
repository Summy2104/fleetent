"""Deterministic retrieval evaluation helpers for knowledge-base fixtures."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fleetent.agent_config import (
    AgentFile,
    AgentModels,
    ModelRouteEntry,
    ModelTarget,
    default_models,
)
from fleetent.config import EmbeddingSettings, KnowledgeBaseSettings, Settings, VectorStoreSettings
from fleetent.db import create_database
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.models import KnowledgeChunk
from fleetent.schema_migrations import migrate

REQUIRED_FIXTURE_FIELDS = (
    "name",
    "documents",
    "queries",
    "expected_chunks",
    "forbidden_chunks",
)
_DEFAULT_TENANT_ID = "default"
_DEFAULT_KB_ID = "global"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "evaluation" / "fixtures" / "knowledge_base_retrieval"


class FixtureValidationError(ValueError):
    """Raised when a knowledge-base retrieval evaluation fixture is invalid."""


class RealEmbeddingEvaluationSkipped(RuntimeError):
    """Raised when a real-embedding evaluation is requested without full config."""


@dataclass(frozen=True)
class RankedHit:
    """Best-ranked expected hit for one query."""

    rank: int
    reciprocal_rank: float
    matched_snippets: list[str]


@dataclass(frozen=True)
class QueryEvaluationResult:
    """Search result, expectations, and ranking metrics for one fixture query."""

    query: str
    chunks: list[KnowledgeChunk]
    expected_chunks: list[str]
    forbidden_chunks: list[str]
    recall_at_k: float
    ranked_hit: RankedHit | None
    forbidden_hits: list[str]


@dataclass(frozen=True)
class RetrievalMetrics:
    """Aggregate retrieval metrics across one or more queries."""

    recall_at_k: float
    mrr: float
    query_count: int
    hit_count: int
    hit_rate: float
    average_hit_rank: float | None


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    """Result captured from one deterministic knowledge-base retrieval evaluation run."""

    fixture_name: str
    db_path: Path
    vector_db_path: Path
    document_count: int
    query_results: list[QueryEvaluationResult]
    metrics: RetrievalMetrics


@dataclass(frozen=True)
class RetrievalEvaluationSuiteResult:
    """Aggregate result from running all configured retrieval fixtures."""

    fixtures: list[RetrievalEvaluationResult]
    metrics: RetrievalMetrics
    hit_ranking: list[dict[str, Any]]


def validate_fixture(fixture: Mapping[str, Any]) -> None:
    """Validate the knowledge-base retrieval evaluation fixture schema."""
    missing = [field for field in REQUIRED_FIXTURE_FIELDS if field not in fixture]
    if missing:
        raise FixtureValidationError(f"missing required fixture fields: {', '.join(missing)}")

    _require_non_empty_string(fixture["name"], "name")
    _require_sequence(fixture["documents"], "documents")
    _require_sequence(fixture["queries"], "queries")
    _require_sequence(fixture["expected_chunks"], "expected_chunks")
    _require_sequence(fixture["forbidden_chunks"], "forbidden_chunks")

    for index, document in enumerate(fixture["documents"]):
        if not isinstance(document, Mapping):
            raise FixtureValidationError(f"documents[{index}] must be an object")
        _require_non_empty_string(document.get("filename"), f"documents[{index}].filename")
        _require_non_empty_string(document.get("content"), f"documents[{index}].content")
        _require_optional_string(document.get("tenant_id"), f"documents[{index}].tenant_id")
        _require_optional_string(document.get("kb_id"), f"documents[{index}].kb_id")

    for index, query in enumerate(fixture["queries"]):
        if not isinstance(query, Mapping):
            raise FixtureValidationError(f"queries[{index}] must be an object")
        _require_non_empty_string(query.get("text"), f"queries[{index}].text")
        _require_optional_string(query.get("tenant_id"), f"queries[{index}].tenant_id")
        _require_sequence(query.get("kb_ids", [_DEFAULT_KB_ID]), f"queries[{index}].kb_ids")
        _require_sequence(query.get("expected_chunks", []), f"queries[{index}].expected_chunks")
        _require_sequence(query.get("forbidden_chunks", []), f"queries[{index}].forbidden_chunks")
        top_k = query.get("top_k", 5)
        if not isinstance(top_k, int) or top_k <= 0:
            raise FixtureValidationError(f"queries[{index}].top_k must be a positive integer")


def load_fixtures(fixture_dir: Path = _FIXTURE_DIR) -> list[dict[str, Any]]:
    """Load and validate knowledge-base retrieval evaluation fixtures."""
    fixtures: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        fixture = json.loads(path.read_text())
        if not isinstance(fixture, dict):
            raise FixtureValidationError(f"{path.name} must contain a fixture object")
        validate_fixture(fixture)
        fixtures.append(fixture)
    return fixtures


async def run_deterministic_fixture(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any | None = None
) -> RetrievalEvaluationResult:
    """Run one fixture through KB ingest and vector search with deterministic embeddings."""
    del monkeypatch
    validate_fixture(fixture)
    db_path = tmp_path / "knowledge-base-retrieval-eval.db"
    vector_db_path = tmp_path / "knowledge-base-retrieval-vectors.db"
    return await _run_fixture(
        fixture,
        db_path=db_path,
        vector_db_path=vector_db_path,
        embedding=EmbeddingSettings(backend="deterministic", dimensions=64),
    )


async def run_real_embedding_fixture(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any | None = None
) -> RetrievalEvaluationResult:
    """Run one fixture with a real HTTP embedding provider when explicitly enabled."""
    del monkeypatch
    if os.environ.get("FLEETENT_EVAL_REAL_EMBEDDING") != "1":
        raise RealEmbeddingEvaluationSkipped(
            "set FLEETENT_EVAL_REAL_EMBEDDING=1 to run real embedding evaluation"
        )

    endpoint = os.environ.get("FLEETENT_EVAL_EMBEDDING_ENDPOINT", "")
    model = os.environ.get("FLEETENT_EVAL_EMBEDDING_MODEL", "")
    api_key = os.environ.get("FLEETENT_EVAL_EMBEDDING_API_KEY", "")
    if not endpoint or not model or not api_key:
        raise RealEmbeddingEvaluationSkipped(
            "real embedding evaluation requires endpoint, model, and API key"
        )

    validate_fixture(fixture)
    db_path = tmp_path / "knowledge-base-retrieval-real-eval.db"
    vector_db_path = tmp_path / "knowledge-base-retrieval-real-vectors.db"
    dimensions = int(os.environ.get("FLEETENT_EVAL_EMBEDDING_DIMENSIONS", "1024"))
    return await _run_fixture(
        fixture,
        db_path=db_path,
        vector_db_path=vector_db_path,
        embedding=EmbeddingSettings(
            backend="http",
            dimensions=dimensions,
            endpoint=endpoint,
            model=model,
            api_key_env="FLEETENT_EVAL_EMBEDDING_API_KEY",
        ),
    )


async def run_deterministic_fixture_suite(
    fixtures: Sequence[Mapping[str, Any]] | None = None,
) -> RetrievalEvaluationSuiteResult:
    """Run all deterministic retrieval fixtures in isolated temporary storage."""
    selected_fixtures = list(fixtures or load_fixtures())
    results: list[RetrievalEvaluationResult] = []
    with tempfile.TemporaryDirectory(prefix="fleetent-kb-eval-") as temp_dir:
        root = Path(temp_dir)
        for index, fixture in enumerate(selected_fixtures):
            fixture_dir = root / f"fixture-{index}"
            fixture_dir.mkdir(parents=True, exist_ok=True)
            results.append(await run_deterministic_fixture(fixture, fixture_dir))
    metrics = _aggregate_metrics(result.metrics for result in results)
    hit_ranking = [
        {
            "fixture_name": result.fixture_name,
            "query": query_result.query,
            "rank": query_result.ranked_hit.rank,
            "reciprocal_rank": query_result.ranked_hit.reciprocal_rank,
            "matched_snippets": query_result.ranked_hit.matched_snippets,
        }
        for result in results
        for query_result in result.query_results
        if query_result.ranked_hit is not None
    ]
    return RetrievalEvaluationSuiteResult(
        fixtures=results,
        metrics=metrics,
        hit_ranking=hit_ranking,
    )


def assert_query_expectations(result: QueryEvaluationResult) -> None:
    """Assert expected snippets are present and forbidden snippets are absent in top-k chunks."""
    contents = [chunk.content for chunk in result.chunks]
    for expected in result.expected_chunks:
        if not _contains_snippet(contents, expected):
            raise AssertionError(f"expected chunk not found: {expected}")
    for forbidden in result.forbidden_chunks:
        if _contains_snippet(contents, forbidden):
            raise AssertionError(f"forbidden chunk found: {forbidden}")


async def _run_fixture(
    fixture: Mapping[str, Any],
    *,
    db_path: Path,
    vector_db_path: Path,
    embedding: EmbeddingSettings,
) -> RetrievalEvaluationResult:
    from fleetent import agent_config
    from fleetent.knowledge_base import runtime as kb_runtime
    from fleetent.vector_store import runtime as vector_runtime

    validate_fixture(fixture)
    _apply_migrations(db_path)
    database_url = f"sqlite:///{db_path}"
    kb_settings = KnowledgeBaseSettings(enabled=True, chunk_size=80, chunk_overlap=0)
    agent = _agent_for_embedding(
        embedding,
        vector_store=VectorStoreSettings(
            backend="sqlite",
            database_url=f"sqlite:///{vector_db_path}",
        ),
    )
    settings = Settings(database_url=database_url)
    database = create_database(database_url)

    with _patched_evaluation_runtime(agent, settings, database, kb_settings):
        document_count = 0
        for document in fixture["documents"]:
            await kb_runtime.ingest_text(
                filename=document["filename"],
                content=document["content"],
                tenant_id=document.get("tenant_id", _DEFAULT_TENANT_ID),
                kb_id=document.get("kb_id", _DEFAULT_KB_ID),
                source=document.get("source", "evaluation"),
                source_url=document.get("source_url"),
            )
            document_count += 1

        query_results: list[QueryEvaluationResult] = []
        for query in fixture["queries"]:
            chunks = await kb_runtime.search(
                query["text"],
                tenant_id=query.get("tenant_id", _DEFAULT_TENANT_ID),
                kb_ids=list(query.get("kb_ids", [_DEFAULT_KB_ID])),
                limit=query.get("top_k", 5),
            )
            query_results.append(
                _evaluate_query_result(
                    query_text=query["text"],
                    chunks=chunks,
                    expected_chunks=list(query.get("expected_chunks", fixture["expected_chunks"])),
                    forbidden_chunks=list(query.get("forbidden_chunks", fixture["forbidden_chunks"])),
                )
            )

    return RetrievalEvaluationResult(
        fixture_name=str(fixture["name"]),
        db_path=db_path,
        vector_db_path=vector_db_path,
        document_count=document_count,
        query_results=query_results,
        metrics=_aggregate_metrics(_metrics_for_query(result) for result in query_results),
    )


def _evaluate_query_result(
    *,
    query_text: str,
    chunks: list[KnowledgeChunk],
    expected_chunks: list[str],
    forbidden_chunks: list[str],
) -> QueryEvaluationResult:
    matched_ranks = _matched_expected_ranks(chunks, expected_chunks)
    forbidden_hits = [
        snippet for snippet in forbidden_chunks if _first_matching_rank(chunks, snippet) is not None
    ]
    recall_at_k = (len(matched_ranks) / len(expected_chunks)) if expected_chunks else 1.0
    best_rank = min(matched_ranks.values(), default=None)
    ranked_hit = None
    if best_rank is not None:
        ranked_hit = RankedHit(
            rank=best_rank,
            reciprocal_rank=1.0 / best_rank,
            matched_snippets=sorted(
                snippet for snippet, rank in matched_ranks.items() if rank == best_rank
            ),
        )
    return QueryEvaluationResult(
        query=query_text,
        chunks=chunks,
        expected_chunks=expected_chunks,
        forbidden_chunks=forbidden_chunks,
        recall_at_k=recall_at_k,
        ranked_hit=ranked_hit,
        forbidden_hits=forbidden_hits,
    )


def _metrics_for_query(result: QueryEvaluationResult) -> RetrievalMetrics:
    return RetrievalMetrics(
        recall_at_k=result.recall_at_k,
        mrr=result.ranked_hit.reciprocal_rank if result.ranked_hit is not None else 0.0,
        query_count=1,
        hit_count=1 if result.ranked_hit is not None else 0,
        hit_rate=1.0 if result.ranked_hit is not None else 0.0,
        average_hit_rank=float(result.ranked_hit.rank) if result.ranked_hit is not None else None,
    )


def _aggregate_metrics(metrics: Sequence[RetrievalMetrics] | Any) -> RetrievalMetrics:
    materialized = list(metrics)
    if not materialized:
        return RetrievalMetrics(
            recall_at_k=0.0,
            mrr=0.0,
            query_count=0,
            hit_count=0,
            hit_rate=0.0,
            average_hit_rank=None,
        )

    query_count = sum(metric.query_count for metric in materialized)
    hit_count = sum(metric.hit_count for metric in materialized)
    hit_ranks = [metric.average_hit_rank for metric in materialized if metric.average_hit_rank]
    return RetrievalMetrics(
        recall_at_k=(
            sum(metric.recall_at_k * metric.query_count for metric in materialized) / query_count
        ),
        mrr=sum(metric.mrr * metric.query_count for metric in materialized) / query_count,
        query_count=query_count,
        hit_count=hit_count,
        hit_rate=(hit_count / query_count) if query_count else 0.0,
        average_hit_rank=(sum(hit_ranks) / len(hit_ranks)) if hit_ranks else None,
    )


@contextmanager
def _patched_evaluation_runtime(
    agent: AgentFile,
    settings: Settings,
    database: Any,
    kb_settings: KnowledgeBaseSettings,
):
    from fleetent import agent_config
    from fleetent.knowledge_base import runtime as kb_runtime
    from fleetent.vector_store import runtime as vector_runtime

    previous_active_agent = agent_config.active_agent_or_default
    previous_settings = kb_runtime._settings
    previous_database = kb_runtime._database
    previous_kb_config = kb_runtime._kb_config
    previous_kb_db = kb_runtime._kb_db
    previous_kb_vector_backend = kb_runtime._kb_vector_backend

    agent_config.active_agent_or_default = lambda: agent
    kb_runtime._settings = lambda: settings
    kb_runtime._database = lambda: database
    kb_runtime._kb_config = lambda: kb_settings
    vector_runtime._configure(agent)
    kb_runtime.set_database(database)
    kb_runtime.set_vector_backend(vector_runtime._backend)
    try:
        yield
    finally:
        agent_config.active_agent_or_default = previous_active_agent
        kb_runtime._settings = previous_settings
        kb_runtime._database = previous_database
        kb_runtime._kb_config = previous_kb_config
        kb_runtime.set_database(previous_kb_db)
        kb_runtime.set_vector_backend(previous_kb_vector_backend)
        vector_runtime._configure(AgentFile(name="", version=0, models=default_models()))


def _apply_migrations(db_path: Path) -> None:
    migrate(create_database(f"sqlite:///{db_path}"), KB_MIGRATIONS)


def _matched_expected_ranks(
    chunks: Sequence[KnowledgeChunk], expected_chunks: Sequence[str]
) -> dict[str, int]:
    matched: dict[str, int] = {}
    for snippet in expected_chunks:
        rank = _first_matching_rank(chunks, snippet)
        if rank is not None:
            matched[snippet] = rank
    return matched


def _first_matching_rank(chunks: Sequence[KnowledgeChunk], snippet: str) -> int | None:
    normalized_snippet = snippet.casefold()
    for index, chunk in enumerate(chunks, start=1):
        if normalized_snippet in chunk.content.casefold():
            return index
    return None


def _agent_for_embedding(
    embedding: EmbeddingSettings,
    *,
    vector_store: VectorStoreSettings,
) -> AgentFile:
    if embedding.backend == "deterministic":
        return AgentFile(name="", version=0, models=default_models(), vector_store=vector_store)
    if embedding.backend == "http":
        return AgentFile(
            name="retrieval-real-embedding-eval",
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


def _require_non_empty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FixtureValidationError(f"{field} must be a non-empty string")


def _require_optional_string(value: object, field: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise FixtureValidationError(f"{field} must be a non-empty string when set")


def _require_sequence(value: object, field: str) -> None:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise FixtureValidationError(f"{field} must be a sequence")


def _contains_snippet(contents: Sequence[str], snippet: str) -> bool:
    normalized_snippet = snippet.casefold()
    return any(normalized_snippet in content.casefold() for content in contents)
