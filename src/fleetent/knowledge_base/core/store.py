import json
import re
from datetime import UTC, datetime

from fleetent.db import Row, SQLiteConnection, SQLiteDatabase
from fleetent.knowledge_base.core.models import KnowledgeChunk, KnowledgeDocument

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


class KnowledgeStore:
    """Database boundary for knowledge-base owned tables.

    Satisfies KnowledgeReadable and KnowledgeWritable via structural subtyping
    (typing.Protocol); no explicit inheritance needed.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def ensure_knowledge_base(self, tenant_id: str, kb_id: str, description: str = "") -> None:
        self._database.execute(
            """
            INSERT OR IGNORE INTO knowledge_bases (
                tenant_id, kb_id, description, created_at, archived_at
            )
            VALUES (:tenant_id, :kb_id, :description, :created_at, NULL)
            """,
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "description": description,
                "created_at": _format_datetime(_now()),
            },
        )

    def update_knowledge_base_description(
        self, tenant_id: str, kb_id: str, description: str
    ) -> bool:
        result = self._database.execute(
            """
            UPDATE knowledge_bases
            SET description = :description
            WHERE tenant_id = :tenant_id
              AND kb_id = :kb_id
            """,
            {"tenant_id": tenant_id, "kb_id": kb_id, "description": description},
        )
        return result.rowcount > 0

    def archive_knowledge_base(self, tenant_id: str, kb_id: str) -> bool:
        result = self._database.execute(
            """
            UPDATE knowledge_bases
            SET archived_at = :archived_at
            WHERE tenant_id = :tenant_id
              AND kb_id = :kb_id
              AND archived_at IS NULL
            """,
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "archived_at": _format_datetime(_now()),
            },
        )
        return result.rowcount > 0

    def has_active_knowledge_base(self, tenant_id: str, kb_id: str) -> bool:
        row = self._database.execute(
            """
            SELECT kb_id
            FROM knowledge_bases
            WHERE tenant_id = :tenant_id
              AND kb_id = :kb_id
              AND archived_at IS NULL
            """,
            {"tenant_id": tenant_id, "kb_id": kb_id},
        ).fetchone()
        return row is not None

    def list_knowledge_bases(self, tenant_id: str) -> list[Row]:
        return self._database.execute(
            """
            SELECT
                kb.tenant_id,
                kb.kb_id,
                kb.description,
                kb.created_at,
                kb.archived_at,
                COUNT(DISTINCT document.id) AS doc_count,
                COUNT(chunk.id) AS chunk_count,
                MAX(document.created_at) AS last_import
            FROM knowledge_bases AS kb
            LEFT JOIN knowledge_documents AS document
              ON document.tenant_id = kb.tenant_id
             AND document.kb_id = kb.kb_id
             AND document.archived_at IS NULL
            LEFT JOIN knowledge_chunks AS chunk
              ON chunk.document_id = document.id
            WHERE kb.tenant_id = :tenant_id
            GROUP BY kb.tenant_id, kb.kb_id, kb.description, kb.created_at, kb.archived_at
            ORDER BY kb.kb_id ASC
            """,
            {"tenant_id": tenant_id},
        ).fetchall()

    def insert_document(self, document: KnowledgeDocument) -> None:
        self._database.execute(_insert_document_sql(), _insert_document_params(document))

    def insert_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        with self._database.transaction() as transaction:
            _insert_chunks(transaction, chunks)

    def list_active_documents_by_identity(
        self, tenant_id: str, kb_id: str, source: str, filename: str
    ) -> list[KnowledgeDocument]:
        rows = self._database.execute(
            """
            SELECT
                document.id,
                document.tenant_id,
                document.kb_id,
                document.filename,
                document.source,
                document.source_url
            FROM knowledge_documents AS document
            JOIN knowledge_bases AS kb
              ON kb.tenant_id = document.tenant_id
             AND kb.kb_id = document.kb_id
            WHERE document.tenant_id = :tenant_id
              AND document.kb_id = :kb_id
              AND document.source = :source
              AND document.filename = :filename
              AND document.archived_at IS NULL
              AND kb.archived_at IS NULL
            ORDER BY document.created_at ASC, document.id ASC
            """,
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "source": source,
                "filename": filename,
            },
        ).fetchall()
        return [_row_to_document(row) for row in rows]

    def replace_document(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
        replaced_document_ids: list[str],
    ) -> None:
        with self._database.transaction() as transaction:
            for replaced_document_id in replaced_document_ids:
                _delete_document_records(transaction, replaced_document_id)
            transaction.execute(_insert_document_sql(), _insert_document_params(document))
            _insert_chunks(transaction, chunks)

    def get_chunks_by_ids(self, tenant_id: str, chunk_ids: list[str]) -> list[KnowledgeChunk]:
        if not chunk_ids:
            return []
        placeholders = ", ".join(f":id_{index}" for index in range(len(chunk_ids)))
        params = {f"id_{index}": chunk_id for index, chunk_id in enumerate(chunk_ids)}
        params["tenant_id"] = tenant_id
        rows = self._database.execute(
            f"""
                SELECT
                    chunk.id,
                    chunk.document_id,
                    chunk.tenant_id,
                    chunk.kb_id,
                    chunk.position,
                    chunk.content,
                    chunk.metadata_json,
                    document.filename,
                    document.source,
                    document.source_url
                FROM knowledge_chunks AS chunk
                JOIN knowledge_documents AS document ON document.id = chunk.document_id
                JOIN knowledge_bases AS kb
                  ON kb.tenant_id = chunk.tenant_id
                 AND kb.kb_id = chunk.kb_id
                WHERE chunk.tenant_id = :tenant_id
                  AND chunk.id IN ({placeholders})
                  AND document.archived_at IS NULL
                  AND kb.archived_at IS NULL
                """,
            params,
        ).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]

    def get_document_chunks(self, document_id: str) -> list[KnowledgeChunk]:
        rows = self._database.execute(
            """
                SELECT
                    chunk.id,
                    chunk.document_id,
                    chunk.tenant_id,
                    chunk.kb_id,
                    chunk.position,
                    chunk.content,
                    chunk.metadata_json,
                    document.filename,
                    document.source,
                    document.source_url
                FROM knowledge_chunks AS chunk
                JOIN knowledge_documents AS document ON document.id = chunk.document_id
                JOIN knowledge_bases AS kb
                  ON kb.tenant_id = chunk.tenant_id
                 AND kb.kb_id = chunk.kb_id
                WHERE chunk.document_id = :document_id
                  AND document.archived_at IS NULL
                  AND kb.archived_at IS NULL
                ORDER BY chunk.position ASC
                """,
            {"document_id": document_id},
        ).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]

    def get_scoped_document_chunks(
        self, tenant_id: str, kb_id: str, document_id: str
    ) -> list[KnowledgeChunk]:
        rows = self._database.execute(
            """
                SELECT
                    chunk.id,
                    chunk.document_id,
                    chunk.tenant_id,
                    chunk.kb_id,
                    chunk.position,
                    chunk.content,
                    chunk.metadata_json,
                    document.filename,
                    document.source,
                    document.source_url
                FROM knowledge_chunks AS chunk
                JOIN knowledge_documents AS document ON document.id = chunk.document_id
                JOIN knowledge_bases AS kb
                  ON kb.tenant_id = chunk.tenant_id
                 AND kb.kb_id = chunk.kb_id
                WHERE chunk.tenant_id = :tenant_id
                  AND chunk.kb_id = :kb_id
                  AND chunk.document_id = :document_id
                  AND document.archived_at IS NULL
                  AND kb.archived_at IS NULL
                ORDER BY chunk.position ASC
                """,
            {"tenant_id": tenant_id, "kb_id": kb_id, "document_id": document_id},
        ).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]

    def has_active_document(self, tenant_id: str, kb_id: str, document_id: str) -> bool:
        row = self._database.execute(
            """
            SELECT document.id
            FROM knowledge_documents AS document
            JOIN knowledge_bases AS kb
              ON kb.tenant_id = document.tenant_id
             AND kb.kb_id = document.kb_id
            WHERE document.tenant_id = :tenant_id
              AND document.kb_id = :kb_id
              AND document.id = :document_id
              AND document.archived_at IS NULL
              AND kb.archived_at IS NULL
            """,
            {"tenant_id": tenant_id, "kb_id": kb_id, "document_id": document_id},
        ).fetchone()
        return row is not None

    def iter_indexable_chunks(self, tenant_id: str, kb_id: str) -> list[KnowledgeChunk]:
        rows = self._database.execute(
            """
                SELECT
                    chunk.id,
                    chunk.document_id,
                    chunk.tenant_id,
                    chunk.kb_id,
                    chunk.position,
                    chunk.content,
                    chunk.metadata_json,
                    document.filename,
                    document.source,
                    document.source_url
                FROM knowledge_chunks AS chunk
                JOIN knowledge_documents AS document ON document.id = chunk.document_id
                JOIN knowledge_bases AS kb
                  ON kb.tenant_id = chunk.tenant_id
                 AND kb.kb_id = chunk.kb_id
                WHERE chunk.tenant_id = :tenant_id
                  AND chunk.kb_id = :kb_id
                  AND document.archived_at IS NULL
                  AND kb.archived_at IS NULL
                ORDER BY chunk.document_id ASC, chunk.position ASC, chunk.id ASC
                """,
            {"tenant_id": tenant_id, "kb_id": kb_id},
        ).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]

    def list_documents(self, tenant_id: str, kb_id: str) -> list[Row]:
        return self._database.execute(
            """
            SELECT
                document.id AS document_id,
                document.filename,
                document.source,
                document.source_url,
                document.created_at,
                COUNT(chunk.id) AS chunks
            FROM knowledge_documents AS document
            JOIN knowledge_bases AS kb
              ON kb.tenant_id = document.tenant_id
             AND kb.kb_id = document.kb_id
            LEFT JOIN knowledge_chunks AS chunk ON chunk.document_id = document.id
            WHERE document.tenant_id = :tenant_id
              AND document.kb_id = :kb_id
              AND document.archived_at IS NULL
              AND kb.archived_at IS NULL
            GROUP BY
                document.id,
                document.filename,
                document.source,
                document.source_url,
                document.created_at
            ORDER BY document.created_at DESC, document.id ASC
            """,
            {"tenant_id": tenant_id, "kb_id": kb_id},
        ).fetchall()

    def preview_document_chunks(
        self, tenant_id: str, kb_id: str, document_id: str
    ) -> list[KnowledgeChunk]:
        rows = self._database.execute(
            """
                SELECT
                    chunk.id,
                    chunk.document_id,
                    chunk.tenant_id,
                    chunk.kb_id,
                    chunk.position,
                    chunk.content,
                    chunk.metadata_json,
                    document.filename,
                    document.source,
                    document.source_url
                FROM knowledge_chunks AS chunk
                JOIN knowledge_documents AS document ON document.id = chunk.document_id
                JOIN knowledge_bases AS kb
                  ON kb.tenant_id = chunk.tenant_id
                 AND kb.kb_id = chunk.kb_id
                WHERE chunk.tenant_id = :tenant_id
                  AND chunk.kb_id = :kb_id
                  AND chunk.document_id = :document_id
                  AND document.archived_at IS NULL
                  AND kb.archived_at IS NULL
                ORDER BY chunk.position ASC
                """,
            {"tenant_id": tenant_id, "kb_id": kb_id, "document_id": document_id},
        ).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]

    def search_keyword(
        self,
        query: str,
        tenant_id: str,
        kb_ids: list[str],
        limit: int,
    ) -> list[KnowledgeChunk]:
        if limit <= 0 or not kb_ids:
            return []
        fts_query = _fts_query(query)
        if not fts_query:
            return []
        placeholders = ", ".join(f":kb_id_{index}" for index in range(len(kb_ids)))
        params: dict[str, object] = {f"kb_id_{index}": kb_id for index, kb_id in enumerate(kb_ids)}
        params.update(
            {
                "query": fts_query,
                "tenant_id": tenant_id,
                "limit": limit,
            }
        )
        rows = self._database.execute(
            f"""
            SELECT
                chunk.id,
                chunk.document_id,
                chunk.tenant_id,
                chunk.kb_id,
                chunk.position,
                chunk.content,
                chunk.metadata_json,
                document.filename,
                document.source,
                document.source_url,
                bm25(knowledge_chunks_fts) AS rank
            FROM knowledge_chunks_fts
            JOIN knowledge_chunks AS chunk ON chunk.id = knowledge_chunks_fts.chunk_id
            JOIN knowledge_documents AS document ON document.id = chunk.document_id
            JOIN knowledge_bases AS kb
              ON kb.tenant_id = chunk.tenant_id
             AND kb.kb_id = chunk.kb_id
            WHERE knowledge_chunks_fts MATCH :query
              AND knowledge_chunks_fts.tenant_id = :tenant_id
              AND knowledge_chunks_fts.kb_id IN ({placeholders})
              AND document.archived_at IS NULL
              AND kb.archived_at IS NULL
            ORDER BY rank ASC, chunk.position ASC, chunk.id ASC
            LIMIT :limit
            """,
            params,
        ).fetchall()
        return [_row_to_chunk(row, score=-float(row["rank"])) for row in rows]

    def archive_document(self, document_id: str) -> None:
        with self._database.transaction() as transaction:
            transaction.execute(
                """
                DELETE FROM knowledge_chunks_fts
                WHERE chunk_id IN (
                    SELECT id
                    FROM knowledge_chunks
                    WHERE document_id = :document_id
                )
                """,
                {"document_id": document_id},
            )
            transaction.execute(
                """
                DELETE FROM knowledge_chunks
                WHERE document_id = :document_id
                """,
                {"document_id": document_id},
            )
            transaction.execute(
                """
                UPDATE knowledge_documents
                SET archived_at = :archived_at
                WHERE id = :document_id
                """,
                {"document_id": document_id, "archived_at": _format_datetime(_now())},
            )

    def delete_document(self, document_id: str) -> None:
        with self._database.transaction() as transaction:
            _delete_document_records(transaction, document_id)

    def delete_scoped_document(self, tenant_id: str, kb_id: str, document_id: str) -> bool:
        if not self.has_active_document(tenant_id, kb_id, document_id):
            return False
        self.delete_document(document_id)
        return True


def _row_to_chunk(row: Row, score: float) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=str(row["id"]),
        document_id=str(row["document_id"]),
        tenant_id=str(row["tenant_id"]),
        kb_id=str(row["kb_id"]),
        filename=str(row["filename"]),
        content=str(row["content"]),
        position=int(row["position"]),
        score=score,
        source=str(row["source"]),
        source_url=str(row["source_url"]) if row["source_url"] is not None else None,
        metadata=_load_metadata(
            str(row["metadata_json"]) if row["metadata_json"] is not None else None
        ),
    )


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _format_datetime(value: datetime) -> str:
    return value.isoformat()


def _dump_metadata(metadata: dict[str, str]) -> str:
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _load_metadata(metadata_json: str | None) -> dict[str, str]:
    if not metadata_json:
        return {}
    raw_metadata = json.loads(metadata_json)
    if not isinstance(raw_metadata, dict):
        return {}
    return {str(key): str(value) for key, value in raw_metadata.items()}


def _row_to_document(row: Row) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        kb_id=str(row["kb_id"]),
        filename=str(row["filename"]),
        source=str(row["source"]),
        source_url=str(row["source_url"]) if row["source_url"] is not None else None,
    )


def _insert_document_sql() -> str:
    return """
        INSERT INTO knowledge_documents (
            id, tenant_id, kb_id, filename, source, source_url, created_at
        )
        VALUES (
            :id, :tenant_id, :kb_id, :filename, :source, :source_url, :created_at
        )
        """


def _insert_document_params(document: KnowledgeDocument) -> dict[str, object]:
    return {
        "id": document.id,
        "tenant_id": document.tenant_id,
        "kb_id": document.kb_id,
        "filename": document.filename,
        "source": document.source,
        "source_url": document.source_url,
        "created_at": _format_datetime(_now()),
    }


def _insert_chunks(transaction: SQLiteConnection, chunks: list[KnowledgeChunk]) -> None:
    for chunk in chunks:
        transaction.execute(
            """
            INSERT INTO knowledge_chunks (
                id, document_id, tenant_id, kb_id, position, content,
                metadata_json, created_at
            )
            VALUES (
                :id, :document_id, :tenant_id, :kb_id, :position, :content,
                :metadata_json, :created_at
            )
            """,
            {
                "id": chunk.id,
                "document_id": chunk.document_id,
                "tenant_id": chunk.tenant_id,
                "kb_id": chunk.kb_id,
                "position": chunk.position,
                "content": chunk.content,
                "metadata_json": _dump_metadata(chunk.metadata),
                "created_at": _format_datetime(_now()),
            },
        )
        transaction.execute(
            """
            INSERT INTO knowledge_chunks_fts (chunk_id, tenant_id, kb_id, content)
            VALUES (:chunk_id, :tenant_id, :kb_id, :content)
            """,
            {
                "chunk_id": chunk.id,
                "tenant_id": chunk.tenant_id,
                "kb_id": chunk.kb_id,
                "content": chunk.content,
            },
        )


def _delete_document_records(transaction: SQLiteConnection, document_id: str) -> None:
    scopes = transaction.execute(
        """
        SELECT tenant_id, kb_id
        FROM knowledge_documents
        WHERE id = :document_id
        UNION
        SELECT tenant_id, kb_id
        FROM knowledge_chunks
        WHERE document_id = :document_id
        UNION
        SELECT tenant_id, kb_id
        FROM kb_entity_mentions
        WHERE document_id = :document_id
        UNION
        SELECT tenant_id, kb_id
        FROM kb_relations
        WHERE evidence_document_id = :document_id
        """,
        {"document_id": document_id},
    ).fetchall()
    transaction.execute(
        """
        DELETE FROM knowledge_chunks_fts
        WHERE chunk_id IN (
            SELECT id
            FROM knowledge_chunks
            WHERE document_id = :document_id
        )
        """,
        {"document_id": document_id},
    )
    transaction.execute(
        """
        DELETE FROM knowledge_chunks
        WHERE document_id = :document_id
        """,
        {"document_id": document_id},
    )
    transaction.execute(
        """
        DELETE FROM kb_entity_mentions
        WHERE document_id = :document_id
        """,
        {"document_id": document_id},
    )
    transaction.execute(
        """
        DELETE FROM kb_relations
        WHERE evidence_document_id = :document_id
        """,
        {"document_id": document_id},
    )
    transaction.execute(
        """
        DELETE FROM knowledge_documents
        WHERE id = :document_id
        """,
        {"document_id": document_id},
    )
    for scope in scopes:
        _delete_orphan_entities(
            transaction,
            tenant_id=str(scope["tenant_id"]),
            kb_id=str(scope["kb_id"]),
        )


def _delete_orphan_entities(transaction: SQLiteConnection, tenant_id: str, kb_id: str) -> None:
    transaction.execute(
        """
        DELETE FROM kb_entities
        WHERE tenant_id = :tenant_id
          AND kb_id = :kb_id
          AND NOT EXISTS (
              SELECT 1
              FROM kb_entity_mentions AS mention
              WHERE mention.tenant_id = kb_entities.tenant_id
                AND mention.kb_id = kb_entities.kb_id
                AND mention.entity_id = kb_entities.id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM kb_relations AS relation
              WHERE relation.tenant_id = kb_entities.tenant_id
                AND relation.kb_id = kb_entities.kb_id
                AND (
                    relation.source_entity_id = kb_entities.id
                    OR relation.target_entity_id = kb_entities.id
                )
          )
        """,
        {"tenant_id": tenant_id, "kb_id": kb_id},
    )


def _fts_query(query: str) -> str:
    tokens = _TOKEN_RE.findall(query)
    terms: list[str] = []
    pending_cjk: list[str] = []
    for token in tokens:
        if _is_cjk(token):
            pending_cjk.append(token)
            continue
        terms.extend(_cjk_terms(pending_cjk))
        pending_cjk = []
        terms.append(token)
    terms.extend(_cjk_terms(pending_cjk))
    return " ".join(f'"{term}"' for term in terms)


def _cjk_terms(chars: list[str]) -> list[str]:
    if len(chars) <= 1:
        return chars
    return ["".join(chars[index : index + 2]) for index in range(len(chars) - 1)]


def _is_cjk(token: str) -> bool:
    return len(token) == 1 and "\u4e00" <= token <= "\u9fff"
