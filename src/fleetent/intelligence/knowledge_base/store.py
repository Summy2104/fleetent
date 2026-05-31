from datetime import UTC, datetime

from fleetent.db import Row, SQLiteDatabase
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument


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
                        id, document_id, tenant_id, kb_id, position, content, created_at
                    )
                    VALUES (
                        :id, :document_id, :tenant_id, :kb_id, :position, :content, :created_at
                    )
                    """,
                    {
                        "id": chunk.id,
                        "document_id": chunk.document_id,
                        "tenant_id": chunk.tenant_id,
                        "kb_id": chunk.kb_id,
                        "position": chunk.position,
                        "content": chunk.content,
                        "created_at": _format_datetime(_now()),
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
                    document.filename,
                    document.source,
                    document.source_url
                FROM knowledge_chunks AS chunk
                JOIN knowledge_documents AS document ON document.id = chunk.document_id
                WHERE chunk.tenant_id = :tenant_id
                  AND chunk.id IN ({placeholders})
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
                    document.filename,
                    document.source,
                    document.source_url
                FROM knowledge_chunks AS chunk
                JOIN knowledge_documents AS document ON document.id = chunk.document_id
                WHERE chunk.document_id = :document_id
                ORDER BY chunk.position ASC
                """,
            {"document_id": document_id},
        ).fetchall()
        return [_row_to_chunk(row, score=0.0) for row in rows]

    def delete_document(self, document_id: str) -> None:
        with self._database.transaction() as transaction:
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
    )


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _format_datetime(value: datetime) -> str:
    return value.isoformat()
