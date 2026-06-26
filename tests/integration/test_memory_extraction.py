import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fleetent import memory as memory_layer
from fleetent import vector_store
from fleetent.db import SQLiteDatabase
from fleetent.memory import extraction, store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def test_parse_action_array_reads_standalone_fenced_json_array() -> None:
    actions = extraction.parse_action_array(
        """
        ```json
        [
          {"action": "create", "type": "identity", "content": "User is a platform engineer"}
        ]
        ```
        """
    )

    assert actions == [
        {"action": "create", "type": "identity", "content": "User is a platform engineer"}
    ]


def test_normalize_action_content_preserves_user_scoped_identity_name() -> None:
    assert (
        extraction.normalize_action_content("identity", "User's name is Randy")
        == "User's name is Randy"
    )


def test_normalize_action_content_preserves_context_initial_acronym() -> None:
    assert (
        extraction.normalize_action_content("context", "Currently AWS migration")
        == "User is currently AWS migration"
    )


def test_normalize_action_content_normalizes_known_role_phrase() -> None:
    assert (
        extraction.normalize_action_content("identity", "Backend engineer")
        == "User is a backend engineer"
    )


def test_normalize_action_content_preserves_ambiguous_identity_text() -> None:
    assert extraction.normalize_action_content("identity", "Analyst fact") == "Analyst fact"


def _patch_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-extraction.db"
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(store, "_state_db", db)
    monkeypatch.setattr(store, "_vector_backend", _TrackingBackend(), raising=False)
    monkeypatch.setattr(vector_store, "embed_text", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    return db_path


def _patch_extraction(monkeypatch, content: str) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(extraction, "AsyncOpenAI", lambda **kwargs: client)


def _memory_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                "SELECT type, content, expires_at FROM memory_items ORDER BY type, content"
            )
        ]


class _TrackingBackend:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[float], str]] = []

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        self.upserts.append((id, vector, namespace))

    async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[object]:
        return []

    async def delete(self, id: str, namespace: str) -> None:
        return None

    async def clear_namespace(self, namespace: str) -> None:
        return None


async def test_extract_and_update_ignores_output_without_valid_json_array(
    tmp_path, monkeypatch
) -> None:
    db_path = _patch_database(tmp_path, monkeypatch)
    upsert = AsyncMock()
    monkeypatch.setattr(vector_store, "upsert", upsert)
    _patch_extraction(
        monkeypatch,
        'Memory actions: {"action": "create", "type": "identity", '
        '"content": "User is a platform engineer"}',
    )

    await memory_layer.extract_and_update("alice", [{"role": "user", "content": "facts"}])

    assert _memory_rows(db_path) == []
    upsert.assert_not_awaited()
