"""KB relation-DB migration list for the Y embedded migration engine.

DDL is the original ensure_schema() content (migrations 006-009, 011, 046),
lifted verbatim.  Schema is intentionally unchanged; tenant_id/kb_id columns
are preserved as seams for future RLS / per-tenant-DB backends.
"""

from __future__ import annotations

_BASE_MIGRATIONS: list[tuple[int, str]] = [
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
    (
        11,
        """
        CREATE TABLE IF NOT EXISTS knowledge_connector_status (
            connector_id        TEXT PRIMARY KEY,
            connector_type      TEXT NOT NULL,
            tenant_id           TEXT NOT NULL,
            kb_id               TEXT NOT NULL,
            last_status         TEXT NOT NULL,
            last_started_at     DATETIME,
            last_finished_at    DATETIME,
            last_summary_json   TEXT NOT NULL,
            last_error          TEXT,
            updated_at          DATETIME NOT NULL
        )
        """,
    ),
    (
        12,
        """
        CREATE TABLE IF NOT EXISTS kb_entities (
            id                  TEXT PRIMARY KEY,
            tenant_id           TEXT NOT NULL,
            kb_id               TEXT NOT NULL,
            entity_type         TEXT NOT NULL,
            name                TEXT NOT NULL,
            normalized_name     TEXT NOT NULL,
            metadata_json       TEXT NOT NULL DEFAULT '{}',
            created_at          DATETIME NOT NULL,
            updated_at          DATETIME NOT NULL,
            UNIQUE (tenant_id, kb_id, entity_type, normalized_name)
        )
        """,
    ),
    (
        13,
        """
        CREATE TABLE IF NOT EXISTS kb_entity_mentions (
            id                  TEXT PRIMARY KEY,
            entity_id           TEXT NOT NULL,
            tenant_id           TEXT NOT NULL,
            kb_id               TEXT NOT NULL,
            document_id         TEXT NOT NULL,
            chunk_id            TEXT NOT NULL,
            text                TEXT NOT NULL,
            confidence          REAL NOT NULL,
            created_at          DATETIME NOT NULL
        )
        """,
    ),
    (
        14,
        """
        CREATE TABLE IF NOT EXISTS kb_relations (
            id                  TEXT PRIMARY KEY,
            tenant_id           TEXT NOT NULL,
            kb_id               TEXT NOT NULL,
            relation_type       TEXT NOT NULL,
            source_entity_id    TEXT NOT NULL,
            target_entity_id    TEXT NOT NULL,
            evidence_document_id TEXT NOT NULL,
            evidence_chunk_id   TEXT NOT NULL,
            evidence_text       TEXT NOT NULL,
            confidence          REAL NOT NULL,
            created_at          DATETIME NOT NULL
        )
        """,
    ),
    (
        15,
        "CREATE INDEX IF NOT EXISTS idx_kb_entity_mentions_document"
        " ON kb_entity_mentions (tenant_id, kb_id, document_id)",
    ),
    (
        16,
        "CREATE INDEX IF NOT EXISTS idx_kb_relations_document"
        " ON kb_relations (tenant_id, kb_id, evidence_document_id)",
    ),
    (
        17,
        """
        CREATE TABLE IF NOT EXISTS knowledge_connector_sync_history (
            id              TEXT PRIMARY KEY,
            connector_id    TEXT NOT NULL,
            tenant_id       TEXT NOT NULL,
            kb_id           TEXT NOT NULL,
            status          TEXT NOT NULL,
            summary_json    TEXT NOT NULL DEFAULT '{}',
            error           TEXT,
            started_at      DATETIME NOT NULL,
            finished_at     DATETIME NOT NULL
        )
        """,
    ),
    (
        18,
        "CREATE INDEX IF NOT EXISTS idx_connector_sync_history_connector"
        " ON knowledge_connector_sync_history (connector_id, finished_at)",
    ),
]

MIGRATIONS: list[tuple[int, str]] = [
    *_BASE_MIGRATIONS,
    (
        _BASE_MIGRATIONS[-1][0] + 1,
        """
        ALTER TABLE knowledge_bases
        ADD COLUMN extraction_enabled INTEGER NOT NULL DEFAULT 0
        """,
    ),
    (
        _BASE_MIGRATIONS[-1][0] + 2,
        """
        ALTER TABLE knowledge_bases
        ADD COLUMN embedding_model TEXT
        """,
    ),
    (
        _BASE_MIGRATIONS[-1][0] + 3,
        """
        ALTER TABLE knowledge_bases
        ADD COLUMN embedding_dimensions INTEGER
        """,
    ),
]
