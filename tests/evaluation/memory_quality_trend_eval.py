import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from fleetent.db import SQLiteDatabase, create_database
from fleetent.intelligence import memory
from tests.integration.test_migrations import apply_migrations

FIXTURE = Path(__file__).parent / "fixtures" / "memory_quality_trend" / "basic.json"


def load_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    """Load the deterministic memory quality trend evaluation fixture."""
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict):
        raise ValueError("memory quality trend fixture must be an object")
    return fixture


def run_fixture(
    fixture: Mapping[str, Any],
    tmp_path: Path,
    monkeypatch: Any,
) -> memory.MemoryQualityTrendSummary:
    """Run the deterministic fixture through the production trend summary API."""
    db_path = tmp_path / "memory-quality-trend-eval.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    database = create_database(f"sqlite:///{db_path}")

    query_data = _mapping(fixture["query"])
    user_id = str(query_data["user_id"])
    for row in _sequence(fixture["user_memories"]):
        _insert_user_memory(database, user_id=user_id, row=_mapping(row))
    for row in _sequence(fixture["shared_memories"]):
        _insert_shared_memory(
            database,
            scope_type=str(query_data["scope_type"]),
            scope_id=str(query_data["scope_id"]),
            row=_mapping(row),
        )

    return memory.get_memory_quality_trend_summary(
        memory.MemoryQualityTrendQuery(
            user_id=user_id,
            scope_type=str(query_data["scope_type"]),
            scope_id=str(query_data["scope_id"]),
            start_ts=_datetime(query_data["start_ts"]),
            end_ts=_datetime(query_data["end_ts"]),
            bucket="day",
        )
    )


def _insert_user_memory(
    database: SQLiteDatabase,
    *,
    user_id: str,
    row: Mapping[str, Any],
) -> None:
    updated_at = _datetime(row["updated_at"])
    expires_at = row.get("expires_at")
    database.execute(
        """
        INSERT INTO memory_items (
            id, user_id, type, content, created_at, updated_at, expires_at
        )
        VALUES (
            :id, :user_id, :type, :content, :created_at, :updated_at, :expires_at
        )
        """,
        {
            "id": str(row["id"]),
            "user_id": user_id,
            "type": str(row["type"]),
            "content": str(row["content"]),
            "created_at": updated_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "expires_at": _datetime(expires_at).isoformat() if expires_at is not None else None,
        },
    )


def _insert_shared_memory(
    database: SQLiteDatabase,
    *,
    scope_type: str,
    scope_id: str,
    row: Mapping[str, Any],
) -> None:
    updated_at = _datetime(row["updated_at"])
    database.execute(
        """
        INSERT INTO shared_memory_items (
            id, scope_type, scope_id, type, content, status, source, source_ref,
            created_by, created_at, updated_at
        )
        VALUES (
            :id, :scope_type, :scope_id, :type, :content, :status, :source, :source_ref,
            :created_by, :created_at, :updated_at
        )
        """,
        {
            "id": str(row["id"]),
            "scope_type": scope_type,
            "scope_id": scope_id,
            "type": str(row["type"]),
            "content": str(row["content"]),
            "status": str(row["status"]),
            "source": "manual",
            "source_ref": None,
            "created_by": "evaluation",
            "created_at": updated_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        },
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected fixture object")
    return value


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected fixture list")
    return value


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected datetime string")
    return datetime.fromisoformat(value)
