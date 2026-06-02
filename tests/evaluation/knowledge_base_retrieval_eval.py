import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from fleetent.config import EmbeddingSettings, KnowledgeBaseSettings, Settings, VectorStoreSettings
from fleetent.db import create_database
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk
from tests.integration.test_migrations import apply_migrations

REQUIRED_FIXTURE_FIELDS = (
    "name",
    "documents",
    "queries",
    "expected_chunks",
    "forbidden_chunks",
)
_DEFAULT_TENANT_ID = "default"
_DEFAULT_KB_ID = "global"
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "knowledge_base_retrieval"


class FixtureValidationError(ValueError):
    """Raised when a knowledge-base retrieval evaluation fixture is invalid."""


@dataclass(frozen=True)
class QueryEvaluationResult:
    """Search result and expectations captured for one fixture query."""

    query: str
    chunks: list[KnowledgeChunk]
    expected_chunks: list[str]
    forbidden_chunks: list[str]


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    """Result captured from a deterministic knowledge-base retrieval evaluation run."""

    db_path: Path
    vector_db_path: Path
    document_count: int
    query_results: list[QueryEvaluationResult]


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
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any
) -> RetrievalEvaluationResult:
    """Run one fixture through KB ingest and vector-only search with local deterministic storage."""
    validate_fixture(fixture)
    db_path = tmp_path / "knowledge-base-retrieval-eval.db"
    vector_db_path = tmp_path / "knowledge-base-retrieval-vectors.db"
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
) -> RetrievalEvaluationResult:
    """Run one fixture with a real HTTP embedding provider when explicitly enabled."""
    if os.environ.get("FLEETENT_EVAL_REAL_EMBEDDING") != "1":
        pytest.skip("set FLEETENT_EVAL_REAL_EMBEDDING=1 to run real embedding evaluation")

    endpoint = os.environ.get("FLEETENT_EVAL_EMBEDDING_ENDPOINT", "")
    model = os.environ.get("FLEETENT_EVAL_EMBEDDING_MODEL", "")
    api_key = os.environ.get("FLEETENT_EVAL_EMBEDDING_API_KEY", "")
    if not endpoint or not model or not api_key:
        pytest.skip("real embedding evaluation requires endpoint, model, and API key")

    db_path = tmp_path / "knowledge-base-retrieval-real-eval.db"
    vector_db_path = tmp_path / "knowledge-base-retrieval-real-vectors.db"
    dimensions = int(os.environ.get("FLEETENT_EVAL_EMBEDDING_DIMENSIONS", "1024"))
    return await _run_fixture(
        fixture,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
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
    tmp_path: Path,
    monkeypatch: Any,
    db_path: Path,
    vector_db_path: Path,
    embedding: EmbeddingSettings,
) -> RetrievalEvaluationResult:
    from fleetent.intelligence.knowledge_base import runtime as kb_runtime
    from fleetent.intelligence.vector_store import runtime as vector_runtime

    apply_migrations(db_path)
    settings = Settings(
        anthropic_api_key="test-key",
        database_url=f"sqlite:///{db_path}",
        vector_store=VectorStoreSettings(
            backend="sqlite",
            database_url=f"sqlite:///{vector_db_path}",
        ),
        embedding=embedding,
        knowledge_base=KnowledgeBaseSettings(
            enabled=True,
            chunk_size=80,
            chunk_overlap=0,
        ),
    )
    database = create_database(settings.database_url)

    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setattr(kb_runtime, "_settings", lambda: settings)
    monkeypatch.setattr(kb_runtime, "_database", lambda: database)
    vector_runtime._configure(settings)

    try:
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
                QueryEvaluationResult(
                    query=query["text"],
                    chunks=chunks,
                    expected_chunks=list(query.get("expected_chunks", fixture["expected_chunks"])),
                    forbidden_chunks=list(
                        query.get("forbidden_chunks", fixture["forbidden_chunks"])
                    ),
                )
            )
        return RetrievalEvaluationResult(
            db_path=db_path,
            vector_db_path=vector_db_path,
            document_count=document_count,
            query_results=query_results,
        )
    finally:
        vector_runtime._configure(Settings(anthropic_api_key=""))


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
