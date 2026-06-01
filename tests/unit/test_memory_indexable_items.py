import sqlite3
from datetime import UTC, datetime, timedelta

from tests.integration.test_migrations import apply_migrations


def _patch_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _insert_memory_row(
    db_path,
    *,
    id: str,
    user_id: str,
    type: str = "identity",
    content: str,
    expires_at: str | None = None,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, type, content, now, now, expires_at),
        )


def test_indexable_item_public_shape_is_importable():
    from dataclasses import fields

    from fleetent.intelligence.vector_store import IndexableItem

    item = IndexableItem(
        id="mem-1",
        content="User likes Python",
        namespace="mem:alice",
        metadata={"type": "preferences"},
    )

    assert [field.name for field in fields(IndexableItem)] == [
        "id",
        "content",
        "namespace",
        "metadata",
    ]
    assert item.id == "mem-1"
    assert item.content == "User likes Python"
    assert item.namespace == "mem:alice"
    assert item.metadata == {"type": "preferences"}


def test_iter_indexable_memories_returns_current_user_items(tmp_path, monkeypatch):
    from fleetent import memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory_row(
        db_path,
        id="alice-identity",
        user_id="alice",
        content="User is a backend engineer",
    )
    _insert_memory_row(
        db_path,
        id="bob-identity",
        user_id="bob",
        content="Bob is unrelated",
    )

    items = list(memory_layer.iter_indexable_memories("alice"))

    assert [(item.id, item.content, item.namespace) for item in items] == [
        ("alice-identity", "User is a backend engineer", "mem:alice")
    ]


def test_iter_indexable_memories_excludes_expired_context(tmp_path, monkeypatch):
    from fleetent import memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory_row(
        db_path,
        id="active-context",
        user_id="alice",
        type="context",
        content="User is working on billing",
        expires_at=(datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat(),
    )
    _insert_memory_row(
        db_path,
        id="expired-context",
        user_id="alice",
        type="context",
        content="User finished the old migration",
        expires_at=(datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)).isoformat(),
    )

    items = list(memory_layer.iter_indexable_memories("alice"))

    assert [(item.id, item.content, item.namespace) for item in items] == [
        ("active-context", "User is working on billing", "mem:alice")
    ]
