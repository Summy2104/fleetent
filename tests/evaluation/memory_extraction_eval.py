import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from fleetent import memory_layer
from fleetent.intelligence import vector_store
from fleetent.intelligence.memory import extraction
from tests.integration.test_migrations import apply_migrations

REQUIRED_FIXTURE_FIELDS = (
    "name",
    "initial_memories",
    "conversation",
    "mock_actions",
    "expected_memories",
    "forbidden_memories",
)
_VALID_ACTIONS = {"create", "update", "delete", "ignore"}
_DEFAULT_USER_ID = "evaluation-user"
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "memory_extraction"
_REAL_LLM_API_KEY_ENVS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")


class FixtureValidationError(ValueError):
    """Raised when a memory extraction evaluation fixture is invalid."""


@dataclass(frozen=True)
class MockEvaluationResult:
    """Result captured from a deterministic memory extraction evaluation run."""

    db_path: Path
    rows: list[dict[str, Any]]
    llm_route_names: list[str]
    vector_upserts: list[tuple[str, str, str]]
    vector_deletes: list[tuple[str, str]]


def validate_fixture(fixture: Mapping[str, Any]) -> None:
    """Validate the memory extraction evaluation fixture schema."""
    missing = [field for field in REQUIRED_FIXTURE_FIELDS if field not in fixture]
    if missing:
        raise FixtureValidationError(f"missing required fixture fields: {', '.join(missing)}")

    _require_non_empty_string(fixture["name"], "name")
    for field in (
        "initial_memories",
        "conversation",
        "mock_actions",
        "expected_memories",
        "forbidden_memories",
    ):
        _require_sequence(fixture[field], field)

    for index, action in enumerate(fixture["mock_actions"]):
        if not isinstance(action, Mapping):
            raise FixtureValidationError(f"mock_actions[{index}] must be an object")
        action_name = action.get("action")
        if action_name not in _VALID_ACTIONS:
            raise FixtureValidationError(f"mock_actions[{index}] has illegal action: {action_name}")


def load_fixtures(fixture_dir: Path = _FIXTURE_DIR) -> list[dict[str, Any]]:
    """Load and validate memory extraction evaluation fixtures."""
    fixtures: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        fixture = json.loads(path.read_text())
        if not isinstance(fixture, dict):
            raise FixtureValidationError(f"{path.name} must contain a fixture object")
        validate_fixture(fixture)
        fixtures.append(fixture)
    return fixtures


async def run_mock_fixture(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any
) -> MockEvaluationResult:
    """Run one fixture through `extract_and_update()` with deterministic mocked actions."""
    validate_fixture(fixture)
    db_path = tmp_path / "memory-extraction-eval.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    _insert_initial_memories(db_path, fixture["initial_memories"])
    route_names: list[str] = []
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(fixture["mock_actions"]))
                )
            ]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    cfg = SimpleNamespace(model="mock-memory-extraction", max_tokens=512)

    def get_mock_client(route_name: str) -> tuple[Any, Any]:
        route_names.append(route_name)
        return client, cfg

    vector_upserts: list[tuple[str, str, str]] = []
    vector_deletes: list[tuple[str, str]] = []

    async def upsert(id: str, text: str, namespace: str) -> None:
        vector_upserts.append((id, text, namespace))

    async def delete(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(extraction, "get_async_client_and_config", get_mock_client)
    monkeypatch.setattr(vector_store, "upsert", upsert)
    monkeypatch.setattr(vector_store, "delete", delete)

    await memory_layer.extract_and_update(_DEFAULT_USER_ID, list(fixture["conversation"]))
    return MockEvaluationResult(
        db_path=db_path,
        rows=memory_rows(db_path),
        llm_route_names=route_names,
        vector_upserts=vector_upserts,
        vector_deletes=vector_deletes,
    )


async def run_real_llm_fixture(
    fixture: Mapping[str, Any], tmp_path: Path, monkeypatch: Any
) -> MockEvaluationResult:
    """Run one fixture through the real memory extraction route when explicitly enabled."""
    if os.environ.get("FLEETENT_EVAL_REAL_LLM") != "1":
        pytest.skip("set FLEETENT_EVAL_REAL_LLM=1 to run real LLM memory evaluation")
    if not any(os.environ.get(env_name) for env_name in _REAL_LLM_API_KEY_ENVS):
        pytest.skip("real LLM memory evaluation requires a provider API key")

    validate_fixture(fixture)
    db_path = tmp_path / "memory-extraction-real-eval.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    _insert_initial_memories(db_path, fixture["initial_memories"])

    route_names: list[str] = []
    vector_upserts: list[tuple[str, str, str]] = []
    vector_deletes: list[tuple[str, str]] = []
    original_get_client = extraction.get_async_client_and_config

    def get_recorded_client(route_name: str) -> tuple[Any, Any]:
        route_names.append(route_name)
        return original_get_client(route_name)

    async def upsert(id: str, text: str, namespace: str) -> None:
        vector_upserts.append((id, text, namespace))

    async def delete(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(extraction, "get_async_client_and_config", get_recorded_client)
    monkeypatch.setattr(vector_store, "upsert", upsert)
    monkeypatch.setattr(vector_store, "delete", delete)

    await memory_layer.extract_and_update(_DEFAULT_USER_ID, list(fixture["conversation"]))
    return MockEvaluationResult(
        db_path=db_path,
        rows=memory_rows(db_path),
        llm_route_names=route_names,
        vector_upserts=vector_upserts,
        vector_deletes=vector_deletes,
    )


def assert_fixture_memory_state(
    rows: Sequence[Mapping[str, Any]], fixture: Mapping[str, Any]
) -> None:
    """Assert final memory rows satisfy expected and forbidden memory states."""
    for expected in fixture["expected_memories"]:
        if not _matching_rows(rows, expected):
            raise AssertionError(f"expected memory not found: {expected}")
    for forbidden in fixture["forbidden_memories"]:
        matches = _matching_rows(rows, forbidden)
        if matches:
            raise AssertionError(f"forbidden memory found: {forbidden}")


def memory_rows(db_path: Path) -> list[dict[str, Any]]:
    """Return deterministic memory rows for evaluation assertions."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, user_id, type, content, created_at, updated_at, expires_at
                FROM memory_items
                ORDER BY type, content, id
                """
            )
        ]


def _require_non_empty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FixtureValidationError(f"{field} must be a non-empty string")


def _require_sequence(value: object, field: str) -> None:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise FixtureValidationError(f"{field} must be a sequence")


def _insert_initial_memories(db_path: Path, memories: object) -> None:
    if not isinstance(memories, Sequence) or isinstance(memories, str):
        raise FixtureValidationError("initial_memories must be a sequence")
    now = datetime.now(UTC).replace(microsecond=0)
    with sqlite3.connect(db_path) as conn:
        for index, memory in enumerate(memories):
            if not isinstance(memory, Mapping):
                raise FixtureValidationError(f"initial_memories[{index}] must be an object")
            created_at = _datetime_from_fixture(memory.get("created_at"), now)
            updated_at = _datetime_from_fixture(memory.get("updated_at"), created_at)
            expires_at = _optional_datetime_from_fixture(memory.get("expires_at"), now)
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
                    "id": memory.get("id", f"fixture-memory-{index}"),
                    "user_id": _DEFAULT_USER_ID,
                    "type": memory["type"],
                    "content": memory["content"],
                    "created_at": created_at.isoformat(),
                    "updated_at": updated_at.isoformat(),
                    "expires_at": expires_at.isoformat() if expires_at else None,
                },
            )


def _matching_rows(
    rows: Sequence[Mapping[str, Any]], expected: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    return [row for row in rows if _row_matches(row, expected)]


def _row_matches(row: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    for field, value in expected.items():
        if field == "expires_at":
            if value == "present" and row.get("expires_at") is None:
                return False
            if value == "absent" and row.get("expires_at") is not None:
                return False
            if value not in {"present", "absent"} and row.get("expires_at") != value:
                return False
            continue
        if row.get(field) != value:
            return False
    return True


def _datetime_from_fixture(value: object, default: datetime) -> datetime:
    if value is None:
        return default
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise FixtureValidationError(
        f"datetime value must be an ISO string, got {type(value).__name__}"
    )


def _optional_datetime_from_fixture(value: object, now: datetime) -> datetime | None:
    if value is None:
        return None
    if value == "future":
        return now + timedelta(days=1)
    if value == "past":
        return now - timedelta(days=1)
    return _datetime_from_fixture(value, now)
