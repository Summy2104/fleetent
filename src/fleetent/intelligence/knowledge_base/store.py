import json
import re
from datetime import UTC, datetime

from fleetent.db import Row, SQLiteDatabase
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


class KnowledgeStore:
    """Database boundary for knowledge-base owned tables."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def ensure_knowledge_base(self, tenant_id: str, kb_id: str) -> None:
        self._database.execute(
            """
            INSERT OR IGNORE INTO knowledge_bases (tenant_id, kb_id, created_at)
            VALUES (:tenant_id, :kb_id, :created_at)
            """,
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "created_at": _format_datetime(_now()),
            },
        )

    def insert_document(self, document: KnowledgeDocument) -> None:
        self._database.execute(
            """
            INSERT INTO knowledge_documents (
                id, tenant_id, kb_id, filename, source, source_url, created_at
            )
            VALUES (
                :id, :tenant_id, :kb_id, :filename, :source, :source_url, :created_at
            )
            """,
            {
                "id": document.id,
                "tenant_id": document.tenant_id,
                "kb_id": document.kb_id,
                "filename": document.filename,
                "source": document.source,
                "source_url": document.source_url,
                "created_at": _format_datetime(_now()),
            },
        )

    def insert_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        with self._database.transaction() as transaction:
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
                WHERE chunk.tenant_id = :tenant_id
                  AND chunk.id IN ({placeholders})
                  AND document.archived_at IS NULL
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
                WHERE chunk.document_id = :document_id
                  AND document.archived_at IS NULL
                ORDER BY chunk.position ASC
                """,
            {"document_id": document_id},
        ).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]

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
                WHERE chunk.tenant_id = :tenant_id
                  AND chunk.kb_id = :kb_id
                  AND document.archived_at IS NULL
                ORDER BY chunk.document_id ASC, chunk.position ASC, chunk.id ASC
                """,
            {"tenant_id": tenant_id, "kb_id": kb_id},
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
            WHERE knowledge_chunks_fts MATCH :query
              AND knowledge_chunks_fts.tenant_id = :tenant_id
              AND knowledge_chunks_fts.kb_id IN ({placeholders})
              AND document.archived_at IS NULL
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
                DELETE FROM knowledge_documents
                WHERE id = :document_id
                """,
                {"document_id": document_id},
            )


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
