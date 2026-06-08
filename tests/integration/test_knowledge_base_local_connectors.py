import hashlib
import sqlite3

import pytest

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def test_migration_creates_local_source_state_table(tmp_path):
    db_path = tmp_path / "knowledge.db"

    apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_source_states)")}
    conn.close()

    assert "knowledge_source_states" in tables
    assert columns >= {
        "source_id",
        "tenant_id",
        "kb_id",
        "source_path",
        "mtime_ns",
        "content_hash",
        "document_id",
        "updated_at",
    }


def test_local_source_state_store_records_path_mtime_hash_and_document(tmp_path):
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    store = LocalSourceStateStore(create_database(f"sqlite:///{db_path}"))
    state = LocalSourceState(
        source_id="local-docs",
        tenant_id="tenant-a",
        kb_id="support",
        source_path="/docs/runbook.md",
        mtime_ns=123,
        content_hash="abc123",
        document_id="doc-1",
    )

    store.upsert(state)

    assert (
        store.get(
            source_id="local-docs",
            tenant_id="tenant-a",
            kb_id="support",
            source_path="/docs/runbook.md",
        )
        == state
    )


def test_local_source_state_store_detects_unchanged_and_changed_files(tmp_path):
    from fleetent.knowledge_base.connectors import (
        LocalSourceState,
        LocalSourceStateStore,
    )

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    store = LocalSourceStateStore(create_database(f"sqlite:///{db_path}"))
    store.upsert(
        LocalSourceState(
            source_id="local-docs",
            tenant_id="tenant-a",
            kb_id="support",
            source_path="/docs/runbook.md",
            mtime_ns=123,
            content_hash="abc123",
            document_id="doc-1",
        )
    )

    assert store.is_unchanged(
        source_id="local-docs",
        tenant_id="tenant-a",
        kb_id="support",
        source_path="/docs/runbook.md",
        mtime_ns=123,
        content_hash="abc123",
    )
    assert not store.is_unchanged(
        source_id="local-docs",
        tenant_id="tenant-a",
        kb_id="support",
        source_path="/docs/runbook.md",
        mtime_ns=124,
        content_hash="abc123",
    )
    assert not store.is_unchanged(
        source_id="local-docs",
        tenant_id="tenant-a",
        kb_id="support",
        source_path="/docs/runbook.md",
        mtime_ns=123,
        content_hash="changed",
    )


async def test_sync_local_directory_ingests_supported_files_into_tenant_kb(
    monkeypatch,
    tmp_path,
):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "runbook.md").write_text("# Runbook\nRestart the worker", encoding="utf-8")
    (root / "notes.txt").write_text("Plain note", encoding="utf-8")
    (root / "page.html").write_text("<h1>Page</h1><p>HTML note</p>", encoding="utf-8")

    from fleetent.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        sync_local_directory,
    )

    summary = await sync_local_directory(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    rows = database.execute(
        """
        SELECT tenant_id, kb_id, filename, source, source_url
        FROM knowledge_documents
        ORDER BY filename ASC
        """,
    ).fetchall()

    assert summary.scanned == 3
    assert summary.ingested == 3
    assert summary.skipped == 0
    assert summary.failed == 0
    assert [(row["tenant_id"], row["kb_id"], row["filename"]) for row in rows] == [
        ("tenant-a", "support", "notes.txt"),
        ("tenant-a", "support", "page.html"),
        ("tenant-a", "support", "runbook.md"),
    ]
    assert {row["source"] for row in rows} == {"local:local-docs"}
    assert {row["source_url"] for row in rows} == {
        str((root / "notes.txt").resolve()),
        str((root / "page.html").resolve()),
        str((root / "runbook.md").resolve()),
    }


async def test_sync_local_directory_skips_unsupported_extensions(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "runbook.md").write_text("# Runbook\nSupported", encoding="utf-8")
    (root / "archive.bin").write_bytes(b"binary")

    from fleetent.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        sync_local_directory,
    )

    summary = await sync_local_directory(
        LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
    )

    assert summary.scanned == 2
    assert summary.ingested == 1
    assert summary.skipped == 1
    assert summary.unsupported == 1
    assert summary.failed == 0


async def test_sync_local_directory_skips_unchanged_files_and_reingests_changed_files(
    monkeypatch,
    tmp_path,
):
    database = _patch_knowledge_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    document_path = root / "runbook.md"
    document_path.write_text("# Runbook\nFirst version", encoding="utf-8")

    from fleetent.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        sync_local_directory,
    )

    config = LocalDirectorySourceConfig(
        source_id="local-docs",
        root_path=root,
        allowed_roots=[root],
    )

    first = await sync_local_directory(config, tenant_id="tenant-a", kb_id="support")
    second = await sync_local_directory(config, tenant_id="tenant-a", kb_id="support")
    document_path.write_text("# Runbook\nSecond version", encoding="utf-8")
    third = await sync_local_directory(config, tenant_id="tenant-a", kb_id="support")

    documents = database.execute(
        """
        SELECT id, filename
        FROM knowledge_documents
        ORDER BY rowid ASC
        """,
    ).fetchall()
    states = database.execute(
        """
        SELECT source_path, content_hash, document_id
        FROM knowledge_source_states
        WHERE source_id = :source_id
        """,
        {"source_id": "local-docs"},
    ).fetchall()

    assert (first.ingested, first.skipped, first.unchanged) == (1, 0, 0)
    assert (second.ingested, second.skipped, second.unchanged) == (0, 1, 1)
    assert (third.ingested, third.skipped, third.unchanged) == (1, 0, 0)
    assert [row["filename"] for row in documents] == ["runbook.md"]
    assert states == [
        {
            "source_path": str(document_path.resolve()),
            "content_hash": hashlib.sha256(b"# Runbook\nSecond version").hexdigest(),
            "document_id": documents[0]["id"],
        }
    ]


async def test_sync_local_directory_rejects_root_outside_allowlist(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()

    from fleetent.knowledge_base.connectors import (
        LocalDirectorySourceConfig,
        sync_local_directory,
    )

    with pytest.raises(ValueError, match="allowlisted root"):
        await sync_local_directory(
            LocalDirectorySourceConfig(
                source_id="local-docs",
                root_path=outside_root,
                allowed_roots=[allowed_root],
            ),
            tenant_id="tenant-a",
            kb_id="support",
        )


def _patch_knowledge_runtime(monkeypatch, tmp_path):
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(chunk_size=100, chunk_overlap=0),
    )
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_settings", lambda: settings)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    return database


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None
