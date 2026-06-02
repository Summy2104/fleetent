import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fleetent.intelligence.memory import MemoryItem

REQUIRED_FIXTURE_FIELDS = (
    "name",
    "user_id",
    "agent_id",
    "query",
    "available_tokens",
    "memories",
    "knowledge",
    "expected_text",
    "forbidden_text",
    "expected_sources",
    "forbidden_sources",
)
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "long_term_context"
_REAL_PROVIDER_ENVS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "FLEETENT_EVAL_EMBEDDING_API_KEY",
)


class FixtureValidationError(ValueError):
    """Raised when a long-term context evaluation fixture is invalid."""


@dataclass(frozen=True)
class ContextEvaluationResult:
    """Result captured from a deterministic long-term context evaluation run."""

    fixture: Mapping[str, Any]
    text: str
    sources: list[tuple[str, str]]
    memory_queries: list[tuple[str, str, int]]
    knowledge_queries: list[tuple[str, str, str, int]]


def validate_fixture(fixture: Mapping[str, Any]) -> None:
    """Validate the long-term context evaluation fixture schema."""
    missing = [field for field in REQUIRED_FIXTURE_FIELDS if field not in fixture]
    if missing:
        raise FixtureValidationError(f"missing required fixture fields: {', '.join(missing)}")

    _require_non_empty_string(fixture["name"], "name")
    _require_non_empty_string(fixture["user_id"], "user_id")
    _require_non_empty_string(fixture["agent_id"], "agent_id")
    _require_non_empty_string(fixture["query"], "query")
    if not isinstance(fixture["available_tokens"], int):
        raise FixtureValidationError("available_tokens must be an integer")

    for field in (
        "memories",
        "knowledge",
        "expected_text",
        "forbidden_text",
        "expected_sources",
        "forbidden_sources",
    ):
        _require_sequence(fixture[field], field)

    for field in ("expected_text", "forbidden_text"):
        _require_string_items(fixture[field], field)

    for field in ("expected_sources", "forbidden_sources"):
        _require_source_assertions(fixture[field], field)


def load_fixtures(fixture_dir: Path = _FIXTURE_DIR) -> list[dict[str, Any]]:
    """Load and validate long-term context evaluation fixtures."""
    fixtures: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        fixture = json.loads(path.read_text())
        if not isinstance(fixture, dict):
            raise FixtureValidationError(f"{path.name} must contain a fixture object")
        validate_fixture(fixture)
        fixtures.append(fixture)
    return fixtures


async def run_deterministic_fixture(
    fixture: Mapping[str, Any], monkeypatch: Any
) -> ContextEvaluationResult:
    """Run one fixture through build_context() with deterministic fake providers."""
    from fleetent.intelligence import long_term_ctx

    validate_fixture(fixture)
    memory_queries: list[tuple[str, str, int]] = []
    knowledge_queries: list[tuple[str, str, str, int]] = []
    memories = [_memory_item(memory, str(fixture["user_id"])) for memory in fixture["memories"]]
    knowledge = [_knowledge_item(item) for item in fixture["knowledge"]]

    async def search_memory(user_id: str, query: str, *, limit: int) -> list[MemoryItem]:
        memory_queries.append((user_id, query, limit))
        return memories[:limit]

    async def search_knowledge(user_id: str, query: str, agent_id: str, limit: int) -> list[object]:
        knowledge_queries.append((user_id, query, agent_id, limit))
        return knowledge[:limit]

    monkeypatch.setattr(long_term_ctx.memory, "search", search_memory)
    long_term_ctx.set_knowledge_provider(search_knowledge)
    try:
        built = await long_term_ctx.build_context(
            user_id=str(fixture["user_id"]),
            query=str(fixture["query"]),
            agent_id=str(fixture["agent_id"]),
            available_tokens=int(fixture["available_tokens"]),
        )
        return ContextEvaluationResult(
            fixture=fixture,
            text=built.text,
            sources=[(source.source_type, source.source_id) for source in built.sources],
            memory_queries=memory_queries,
            knowledge_queries=knowledge_queries,
        )
    finally:
        long_term_ctx.set_knowledge_provider(None)


async def run_real_provider_smoke(fixture: Mapping[str, Any]) -> ContextEvaluationResult:
    """Run a real-provider smoke only when explicitly enabled and configured."""
    if os.environ.get("FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT") != "1":
        pytest.skip(
            "set FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1 to run real long-term context smoke"
        )
    if not any(os.environ.get(env_name) for env_name in _REAL_PROVIDER_ENVS):
        pytest.skip("real long-term context smoke requires provider credentials/config")

    from fleetent.intelligence import long_term_ctx

    validate_fixture(fixture)
    built = await long_term_ctx.build_context(
        user_id=str(fixture["user_id"]),
        query=str(fixture["query"]),
        agent_id=str(fixture["agent_id"]),
        available_tokens=int(fixture["available_tokens"]),
    )
    return ContextEvaluationResult(
        fixture=fixture,
        text=built.text,
        sources=[(source.source_type, source.source_id) for source in built.sources],
        memory_queries=[],
        knowledge_queries=[],
    )


def assert_context_expectations(result: ContextEvaluationResult) -> None:
    """Assert built context satisfies expected and forbidden fixture assertions."""
    for expected in result.fixture["expected_text"]:
        if expected not in result.text:
            raise AssertionError(f"expected text not found: {expected}")
    for forbidden in result.fixture["forbidden_text"]:
        if forbidden in result.text:
            raise AssertionError(f"forbidden text found: {forbidden}")

    for expected in result.fixture["expected_sources"]:
        source = (expected["source_type"], expected["source_id"])
        if source not in result.sources:
            raise AssertionError(f"expected source not found: {source}")
    for forbidden in result.fixture["forbidden_sources"]:
        source = (forbidden["source_type"], forbidden["source_id"])
        if source in result.sources:
            raise AssertionError(f"forbidden source found: {source}")


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


def _require_source_assertions(value: object, field: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise FixtureValidationError(f"{field} must be a sequence")
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise FixtureValidationError(f"{field}[{index}] must be an object")
        _require_non_empty_string(item.get("source_type"), f"{field}[{index}].source_type")
        _require_non_empty_string(item.get("source_id"), f"{field}[{index}].source_id")


def _memory_item(memory: Mapping[str, Any], user_id: str) -> MemoryItem:
    now = datetime.now(UTC).replace(microsecond=0)
    return MemoryItem(
        id=str(memory["id"]),
        user_id=user_id,
        type=str(memory["type"]),
        content=str(memory["content"]),
        created_at=now,
        updated_at=now,
        expires_at=None,
    )


def _knowledge_item(item: Mapping[str, Any]) -> object:
    metadata = item.get("metadata", {})
    return SimpleNamespace(
        id=str(item["id"]),
        content=str(item["content"]),
        score=float(item.get("score", 1.0)),
        metadata=metadata if isinstance(metadata, dict) else {},
    )
