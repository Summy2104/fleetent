"""Deterministic retrieval evaluation helpers for knowledge-base fixtures."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator, Mapping, Sequence
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
from fleetent.config import (
    EmbeddingSettings,
    KnowledgeBaseSettings,
    RerankSettings,
    Settings,
    VectorStoreSettings,
)
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
# Retrieval modes a fixture query may select. Defaulting to vector keeps every
# pre-existing fixture (which carries no mode) behaving exactly as before.
SUPPORTED_QUERY_MODES = ("vector", "keyword", "hybrid")
DEFAULT_QUERY_MODE = "vector"

# Retrieval quality is a property of the vector backend as much as of the embedding, so the
# harness has to be able to point at whichever one a deployment actually runs. sqlite stays the
# default because every existing caller relies on it.
SUPPORTED_VECTOR_BACKENDS = ("sqlite", "milvus")
DEFAULT_VECTOR_BACKEND = "sqlite"

# A fixture may declare that it only means anything under a real semantic embedding. Such a
# fixture is expected to score *zero* with the deterministic provider — that is what proves it
# measures semantics rather than word overlap — so it must be excluded from the suite-wide
# "every fixture scores 1.0" expectation instead of silently dragging it down.
SUPPORTED_FIXTURE_REQUIREMENTS = ("semantic_embedding",)

# Rerank is off unless a run asks for it: a fixture run must never reach out to a reranker by
# accident. The provider comes from the agent's top-level ``rerank`` block, which is what
# ``knowledge_base.retrieval.search`` actually reads — the model-route path exists but no
# production caller uses it, so wiring the block is what makes rerank real here.
SUPPORTED_RERANK_BACKENDS = ("disabled", "deterministic", "http")
DEFAULT_RERANK_BACKEND = "disabled"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "evaluation" / "fixtures" / "knowledge_base_retrieval"


class FixtureValidationError(ValueError):
    """Raised when a knowledge-base retrieval evaluation fixture is invalid."""


class RealEmbeddingEvaluationSkipped(RuntimeError):  # noqa: N818 — a skip signal, not a failure
    """Raised when a real-embedding evaluation is requested without full config.

    Deliberately not named ``...Error``: missing provider credentials is the normal state for a
    run without them, and callers translate this into a skip. An ``Error`` suffix would invite
    treating it as a failure.
    """


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
        _validate_query_search_mode(query, index)

    _validate_fixture_requirement(fixture)


def requires_semantic_embedding(fixture: Mapping[str, Any]) -> bool:
    """Whether this fixture only produces a meaningful score under a real embedding model."""
    return fixture.get("requires") == "semantic_embedding"


def _validate_fixture_requirement(fixture: Mapping[str, Any]) -> None:
    requirement = fixture.get("requires")
    if requirement is None:
        return
    if requirement not in SUPPORTED_FIXTURE_REQUIREMENTS:
        raise FixtureValidationError(
            f"requires must be one of {', '.join(SUPPORTED_FIXTURE_REQUIREMENTS)}, "
            f"got {requirement!r}"
        )


def _validate_query_search_mode(query: Mapping[str, Any], index: int) -> None:
    """Validate the optional per-query retrieval mode and rerank flag.

    Absent fields keep the historical behaviour (vector search, no rerank), so existing
    fixtures stay valid. The rerank/hybrid coupling mirrors the runtime contract in
    ``knowledge_base.runtime.search`` — rejecting it here surfaces the mismatch at fixture
    load time rather than as a ValueError mid-run.
    """
    mode = query.get("mode", DEFAULT_QUERY_MODE)
    if mode not in SUPPORTED_QUERY_MODES:
        raise FixtureValidationError(
            f"queries[{index}].mode must be one of {', '.join(SUPPORTED_QUERY_MODES)}"
        )
    rerank = query.get("rerank", False)
    if not isinstance(rerank, bool):
        raise FixtureValidationError(f"queries[{index}].rerank must be a boolean")
    if rerank and mode != "hybrid":
        raise FixtureValidationError(f"queries[{index}].rerank requires hybrid mode, got {mode!r}")


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
    fixture: Mapping[str, Any],
    tmp_path: Path,
    monkeypatch: Any | None = None,
    *,
    vector_backend: str = DEFAULT_VECTOR_BACKEND,
    rerank_backend: str = DEFAULT_RERANK_BACKEND,
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
        vector_backend=vector_backend,
        rerank=_rerank_settings(rerank_backend),
    )


async def run_real_embedding_fixture(
    fixture: Mapping[str, Any],
    tmp_path: Path,
    monkeypatch: Any | None = None,
    *,
    vector_backend: str = DEFAULT_VECTOR_BACKEND,
    rerank_backend: str = DEFAULT_RERANK_BACKEND,
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
        vector_backend=vector_backend,
        rerank=_rerank_settings(rerank_backend),
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
    vector_backend: str = DEFAULT_VECTOR_BACKEND,
    rerank: RerankSettings | None = None,
) -> RetrievalEvaluationResult:
    from fleetent.knowledge_base import runtime as kb_runtime

    validate_fixture(fixture)
    _apply_migrations(db_path)
    database_url = f"sqlite:///{db_path}"
    kb_settings = KnowledgeBaseSettings(enabled=True, chunk_size=80, chunk_overlap=0)
    agent = _agent_for_embedding(
        embedding,
        vector_store=_vector_store_settings(vector_backend, vector_db_path),
        rerank=rerank,
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
                mode=query.get("mode", DEFAULT_QUERY_MODE),
                rerank=bool(query.get("rerank", False)),
            )
            query_results.append(
                _evaluate_query_result(
                    query_text=query["text"],
                    chunks=chunks,
                    expected_chunks=list(query.get("expected_chunks", fixture["expected_chunks"])),
                    forbidden_chunks=list(
                        query.get("forbidden_chunks", fixture["forbidden_chunks"])
                    ),
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
) -> Iterator[None]:
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


def _vector_store_settings(vector_backend: str, vector_db_path: Path) -> VectorStoreSettings:
    """Map a backend name onto the url scheme that backend expects.

    Callers pass a name rather than a url so a fixture run cannot pair ``milvus`` with a
    ``sqlite://`` url; the schemes are not interchangeable and the mismatch would only surface
    deep inside the backend.
    """
    if vector_backend == "sqlite":
        return VectorStoreSettings(backend="sqlite", database_url=f"sqlite:///{vector_db_path}")
    if vector_backend == "milvus":
        return VectorStoreSettings(backend="milvus", database_url=f"milvus:///{vector_db_path}")
    raise FixtureValidationError(
        f"unsupported vector backend: {vector_backend!r}. "
        f"Supported: {', '.join(SUPPORTED_VECTOR_BACKENDS)}"
    )


def _rerank_settings(rerank_backend: str) -> RerankSettings:
    """Build the agent's top-level rerank block for a fixture run.

    The http backend reads endpoint/model/key from ``FLEETENT_EVAL_RERANK_*`` for the same reason
    the embedding path does: a credential must not be able to reach a fixture file.
    """
    if rerank_backend not in SUPPORTED_RERANK_BACKENDS:
        raise FixtureValidationError(
            f"unsupported rerank backend: {rerank_backend!r}. "
            f"Supported: {', '.join(SUPPORTED_RERANK_BACKENDS)}"
        )
    if rerank_backend != "http":
        return RerankSettings(backend=rerank_backend)

    endpoint = os.environ.get("FLEETENT_EVAL_RERANK_ENDPOINT", "")
    model = os.environ.get("FLEETENT_EVAL_RERANK_MODEL", "")
    if not endpoint or not model or not os.environ.get("FLEETENT_EVAL_RERANK_API_KEY"):
        raise RealEmbeddingEvaluationSkipped(
            "http rerank evaluation requires FLEETENT_EVAL_RERANK_ENDPOINT, "
            "FLEETENT_EVAL_RERANK_MODEL, and FLEETENT_EVAL_RERANK_API_KEY"
        )
    return RerankSettings(
        backend="http",
        endpoint=endpoint,
        model=model,
        api_key_env="FLEETENT_EVAL_RERANK_API_KEY",
    )


def _agent_for_embedding(
    embedding: EmbeddingSettings,
    *,
    vector_store: VectorStoreSettings,
    rerank: RerankSettings | None = None,
) -> AgentFile:
    resolved_rerank = rerank or RerankSettings()
    if embedding.backend == "deterministic":
        return AgentFile(
            name="",
            version=0,
            models=default_models(),
            vector_store=vector_store,
            rerank=resolved_rerank,
        )
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
            rerank=resolved_rerank,
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
