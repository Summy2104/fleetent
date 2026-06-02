import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fleetent.db import Row, SQLiteConnection, SQLiteDatabase
from fleetent.intelligence.knowledge_base.extraction import ExtractedEntity, ExtractedRelation


@dataclass(frozen=True)
class KnowledgeEntity:
    """Canonical entity scoped to one tenant knowledge base."""

    id: str
    tenant_id: str
    kb_id: str
    entity_type: str
    name: str
    normalized_name: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class KnowledgeExtractionRun:
    """Persisted entity extraction run summary."""

    id: str
    tenant_id: str
    kb_id: str
    document_id: str | None
    extractor: str
    status: str
    documents_scanned: int
    chunks_scanned: int
    entities_upserted: int
    mentions_written: int
    relations_written: int
    failed_count: int
    error_summary: str | None = None


class KnowledgeEntityStore:
    """Database boundary for knowledge-base entity extraction tables."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def upsert_entity(
        self,
        tenant_id: str,
        kb_id: str,
        entity: ExtractedEntity,
    ) -> KnowledgeEntity:
        """Upsert a canonical entity by tenant + KB + type + normalized name."""

        now = _format_datetime(_now())
        existing = self._database.execute(
            """
            SELECT id, tenant_id, kb_id, entity_type, name, normalized_name, metadata_json
            FROM kb_entities
            WHERE tenant_id = :tenant_id
              AND kb_id = :kb_id
              AND entity_type = :entity_type
              AND normalized_name = :normalized_name
            """,
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "entity_type": entity.entity_type,
                "normalized_name": entity.normalized_name,
            },
        ).fetchone()
        if existing is not None:
            return _row_to_entity(existing)

        entity_id = str(uuid.uuid4())
        self._database.execute(
            """
            INSERT INTO kb_entities (
                id, tenant_id, kb_id, entity_type, name, normalized_name,
                metadata_json, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :kb_id, :entity_type, :name, :normalized_name,
                :metadata_json, :created_at, :updated_at
            )
            """,
            {
                "id": entity_id,
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "entity_type": entity.entity_type,
                "name": entity.name.strip(),
                "normalized_name": entity.normalized_name,
                "metadata_json": json.dumps(entity.metadata, sort_keys=True),
                "created_at": now,
                "updated_at": now,
            },
        )
        row = self._database.execute(
            """
            SELECT id, tenant_id, kb_id, entity_type, name, normalized_name, metadata_json
            FROM kb_entities
            WHERE id = :id
            """,
            {"id": entity_id},
        ).fetchone()
        if row is None:
            raise RuntimeError("inserted entity was not found")
        return _row_to_entity(row)

    def insert_run(
        self,
        *,
        tenant_id: str,
        kb_id: str,
        document_id: str | None,
        extractor: str,
    ) -> KnowledgeExtractionRun:
        """Create a running extraction run summary."""

        run_id = str(uuid.uuid4())
        started_at = _format_datetime(_now())
        self._database.execute(
            """
            INSERT INTO kb_extraction_runs (
                id, tenant_id, kb_id, document_id, extractor, status, started_at,
                finished_at, documents_scanned, chunks_scanned, entities_upserted,
                mentions_written, relations_written, failed_count, error_summary,
                metadata_json
            )
            VALUES (
                :id, :tenant_id, :kb_id, :document_id, :extractor, :status, :started_at,
                NULL, 0, 0, 0, 0, 0, 0, NULL, :metadata_json
            )
            """,
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "document_id": document_id,
                "extractor": extractor,
                "status": "running",
                "started_at": started_at,
                "metadata_json": "{}",
            },
        )
        return KnowledgeExtractionRun(
            id=run_id,
            tenant_id=tenant_id,
            kb_id=kb_id,
            document_id=document_id,
            extractor=extractor,
            status="running",
            documents_scanned=0,
            chunks_scanned=0,
            entities_upserted=0,
            mentions_written=0,
            relations_written=0,
            failed_count=0,
        )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        documents_scanned: int,
        chunks_scanned: int,
        entities_upserted: int,
        mentions_written: int,
        relations_written: int,
        failed_count: int,
        error_summary: str | None = None,
    ) -> KnowledgeExtractionRun:
        """Finalize an extraction run and return the persisted summary."""

        self._database.execute(
            """
            UPDATE kb_extraction_runs
            SET status = :status,
                finished_at = :finished_at,
                documents_scanned = :documents_scanned,
                chunks_scanned = :chunks_scanned,
                entities_upserted = :entities_upserted,
                mentions_written = :mentions_written,
                relations_written = :relations_written,
                failed_count = :failed_count,
                error_summary = :error_summary
            WHERE id = :run_id
            """,
            {
                "status": status,
                "finished_at": _format_datetime(_now()),
                "documents_scanned": documents_scanned,
                "chunks_scanned": chunks_scanned,
                "entities_upserted": entities_upserted,
                "mentions_written": mentions_written,
                "relations_written": relations_written,
                "failed_count": failed_count,
                "error_summary": error_summary,
                "run_id": run_id,
            },
        )
        row = self._database.execute(
            """
            SELECT id, tenant_id, kb_id, document_id, extractor, status,
                   documents_scanned, chunks_scanned, entities_upserted,
                   mentions_written, relations_written, failed_count, error_summary
            FROM kb_extraction_runs
            WHERE id = :run_id
            """,
            {"run_id": run_id},
        ).fetchone()
        if row is None:
            raise RuntimeError("finished extraction run was not found")
        return _row_to_run(row)

    def replace_document_evidence(
        self,
        *,
        tenant_id: str,
        kb_id: str,
        document_id: str,
        run_id: str,
        entities: list[ExtractedEntity],
        relations: list[ExtractedRelation],
    ) -> tuple[int, int, int]:
        """Replace active mentions and relations for one successfully extracted document."""

        with self._database.transaction() as transaction:
            entity_by_key: dict[tuple[str, str], KnowledgeEntity] = {}
            for entity in entities:
                canonical = self._upsert_entity(transaction, tenant_id, kb_id, entity)
                entity_by_key[(entity.entity_type, entity.normalized_name)] = canonical

            transaction.execute(
                """
                DELETE FROM kb_entity_mentions
                WHERE tenant_id = :tenant_id AND kb_id = :kb_id AND document_id = :document_id
                """,
                {"tenant_id": tenant_id, "kb_id": kb_id, "document_id": document_id},
            )
            transaction.execute(
                """
                DELETE FROM kb_relations
                WHERE tenant_id = :tenant_id
                  AND kb_id = :kb_id
                  AND evidence_document_id = :document_id
                """,
                {"tenant_id": tenant_id, "kb_id": kb_id, "document_id": document_id},
            )
            mentions_written = 0
            for entity in entities:
                canonical = entity_by_key[(entity.entity_type, entity.normalized_name)]
                transaction.execute(
                    """
                    INSERT INTO kb_entity_mentions (
                        id, entity_id, tenant_id, kb_id, document_id, chunk_id, text,
                        confidence, extraction_run_id, created_at
                    )
                    VALUES (
                        :id, :entity_id, :tenant_id, :kb_id, :document_id, :chunk_id, :text,
                        :confidence, :extraction_run_id, :created_at
                    )
                    """,
                    {
                        "id": str(uuid.uuid4()),
                        "entity_id": canonical.id,
                        "tenant_id": tenant_id,
                        "kb_id": kb_id,
                        "document_id": document_id,
                        "chunk_id": str(entity.metadata.get("chunk_id", "")),
                        "text": entity.name.strip(),
                        "confidence": entity.confidence,
                        "extraction_run_id": run_id,
                        "created_at": _format_datetime(_now()),
                    },
                )
                mentions_written += 1

            relations_written = 0
            for relation in relations:
                source = entity_by_key[
                    (relation.source.entity_type, relation.source.normalized_name)
                ]
                target = entity_by_key[
                    (relation.target.entity_type, relation.target.normalized_name)
                ]
                transaction.execute(
                    """
                    INSERT INTO kb_relations (
                        id, tenant_id, kb_id, relation_type, source_entity_id,
                        target_entity_id, evidence_document_id, evidence_chunk_id,
                        evidence_text, confidence, extraction_run_id, created_at
                    )
                    VALUES (
                        :id, :tenant_id, :kb_id, :relation_type, :source_entity_id,
                        :target_entity_id, :evidence_document_id, :evidence_chunk_id,
                        :evidence_text, :confidence, :extraction_run_id, :created_at
                    )
                    """,
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "kb_id": kb_id,
                        "relation_type": relation.relation_type,
                        "source_entity_id": source.id,
                        "target_entity_id": target.id,
                        "evidence_document_id": relation.document_id,
                        "evidence_chunk_id": relation.chunk_id,
                        "evidence_text": _summarize_evidence(relation.evidence_text),
                        "confidence": relation.confidence,
                        "extraction_run_id": run_id,
                        "created_at": _format_datetime(_now()),
                    },
                )
                relations_written += 1
        return len(entity_by_key), mentions_written, relations_written

    def _upsert_entity(
        self,
        transaction: SQLiteConnection,
        tenant_id: str,
        kb_id: str,
        entity: ExtractedEntity,
    ) -> KnowledgeEntity:
        existing = transaction.execute(
            """
            SELECT id, tenant_id, kb_id, entity_type, name, normalized_name, metadata_json
            FROM kb_entities
            WHERE tenant_id = :tenant_id
              AND kb_id = :kb_id
              AND entity_type = :entity_type
              AND normalized_name = :normalized_name
            """,
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "entity_type": entity.entity_type,
                "normalized_name": entity.normalized_name,
            },
        ).fetchone()
        if existing is not None:
            return _row_to_entity(existing)
        entity_id = str(uuid.uuid4())
        now = _format_datetime(_now())
        transaction.execute(
            """
            INSERT INTO kb_entities (
                id, tenant_id, kb_id, entity_type, name, normalized_name,
                metadata_json, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :kb_id, :entity_type, :name, :normalized_name,
                :metadata_json, :created_at, :updated_at
            )
            """,
            {
                "id": entity_id,
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "entity_type": entity.entity_type,
                "name": entity.name.strip(),
                "normalized_name": entity.normalized_name,
                "metadata_json": json.dumps(entity.metadata, sort_keys=True),
                "created_at": now,
                "updated_at": now,
            },
        )
        return KnowledgeEntity(
            id=entity_id,
            tenant_id=tenant_id,
            kb_id=kb_id,
            entity_type=entity.entity_type,
            name=entity.name.strip(),
            normalized_name=entity.normalized_name,
            metadata=entity.metadata,
        )


def _row_to_entity(row: Row) -> KnowledgeEntity:
    return KnowledgeEntity(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        kb_id=str(row["kb_id"]),
        entity_type=str(row["entity_type"]),
        name=str(row["name"]),
        normalized_name=str(row["normalized_name"]),
        metadata=json.loads(str(row["metadata_json"])),
    )


def _row_to_run(row: Row) -> KnowledgeExtractionRun:
    return KnowledgeExtractionRun(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        kb_id=str(row["kb_id"]),
        document_id=str(row["document_id"]) if row["document_id"] is not None else None,
        extractor=str(row["extractor"]),
        status=str(row["status"]),
        documents_scanned=int(row["documents_scanned"]),
        chunks_scanned=int(row["chunks_scanned"]),
        entities_upserted=int(row["entities_upserted"]),
        mentions_written=int(row["mentions_written"]),
        relations_written=int(row["relations_written"]),
        failed_count=int(row["failed_count"]),
        error_summary=(str(row["error_summary"]) if row["error_summary"] is not None else None),
    )


def _summarize_evidence(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _now() -> datetime:
    return datetime.now(UTC)


def _format_datetime(value: datetime) -> str:
    return value.isoformat()
