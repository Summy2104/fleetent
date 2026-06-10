"""KB relation-DB migration list for the Y embedded migration engine.

DDL is the original ensure_schema() content (migrations 006-009, 011, 046),
lifted verbatim.  Schema is intentionally unchanged; tenant_id/kb_id columns
are preserved as seams for future RLS / per-tenant-DB backends.
"""

from __future__ import annotations

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            tenant_id   TEXT NOT NULL,
            kb_id       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            archived_at TEXT,
            PRIMARY KEY (tenant_id, kb_id)
        )
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id          TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            kb_id       TEXT NOT NULL,
            filename    TEXT NOT NULL,
            source      TEXT NOT NULL,
            source_url  TEXT,
            created_at  TEXT NOT NULL,
            archived_at TEXT,
            FOREIGN KEY (tenant_id, kb_id)
                REFERENCES knowledge_bases (tenant_id, kb_id) ON DELETE CASCADE
        )
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id              TEXT PRIMARY KEY,
            document_id     TEXT NOT NULL,
            tenant_id       TEXT NOT NULL,
            kb_id           TEXT NOT NULL,
            position        INTEGER NOT NULL,
            content         TEXT NOT NULL,
            metadata_json   TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL,
            FOREIGN KEY (document_id)
                REFERENCES knowledge_documents (id) ON DELETE CASCADE
        )
        """,
    ),
    (
        4,
        """
        CREATE TABLE IF NOT EXISTS knowledge_source_states (
            source_id       TEXT NOT NULL,
            tenant_id       TEXT NOT NULL,
            kb_id           TEXT NOT NULL,
            source_path     TEXT NOT NULL,
            mtime_ns        INTEGER NOT NULL,
            content_hash    TEXT NOT NULL,
            document_id     TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            PRIMARY KEY (source_id, tenant_id, kb_id, source_path)
        )
        """,
    ),
    (
        5,
        "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_archive"
        " ON knowledge_bases (tenant_id, archived_at)",
    ),
    (
        6,
        "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_scope"
        " ON knowledge_documents (tenant_id, kb_id)",
    ),
    (
        7,
        "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_archive"
        " ON knowledge_documents (tenant_id, kb_id, archived_at)",
    ),
    (
        8,
        "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document_position"
        " ON knowledge_chunks (document_id, position)",
    ),
    (
        9,
        "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_scope"
        " ON knowledge_chunks (tenant_id, kb_id)",
    ),
    (
        10,
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
        USING fts5(
            chunk_id UNINDEXED,
            tenant_id UNINDEXED,
            kb_id UNINDEXED,
            content,
            tokenize = 'unicode61'
        )
        """,
    ),
]
