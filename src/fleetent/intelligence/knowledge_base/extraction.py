from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fleetent.intelligence.knowledge_base.extraction_store import KnowledgeExtractionRun

SUPPORTED_ENTITY_TYPES = frozenset(
    {
        "person",
        "team",
        "organization",
        "customer",
        "project",
        "system",
        "document",
        "concept",
        "term",
    }
)
SUPPORTED_RELATION_TYPES = frozenset(
    {
        "mentions",
        "belongs_to",
        "owns",
        "depends_on",
        "related_to",
        "defines",
        "conflicts_with",
    }
)
_WHITESPACE_RE = re.compile(r"\s+")
_ENTITY_LABELS = {
    "person": "person",
    "team": "team",
    "organization": "organization",
    "customer": "customer",
    "project": "project",
    "system": "system",
    "document": "document",
    "concept": "concept",
    "term": "term",
}


@dataclass(frozen=True)
class ExtractedEntity:
    """Entity emitted by a knowledge-base extractor before canonical upsert."""

    entity_type: str
    name: str
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def normalized_name(self) -> str:
        return normalize_entity_name(self.name)

    def __post_init__(self) -> None:
        validate_entity_type(self.entity_type)
        if not self.normalized_name:
            raise ValueError("entity name must not be empty")


@dataclass(frozen=True)
class ExtractedRelation:
    """Relation emitted by a knowledge-base extractor with chunk evidence."""

    relation_type: str
    source: ExtractedEntity
    target: ExtractedEntity
    evidence_text: str
    chunk_id: str
    document_id: str
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_relation_type(self.relation_type)
        if not self.evidence_text.strip():
            raise ValueError("relation evidence_text must not be empty")


@dataclass(frozen=True)
class ExtractionResult:
    """Deterministic extractor output for one chunk."""

    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]


@dataclass(frozen=True)
class ExtractionSmokeResult:
    """Result for optional real LLM entity extraction smoke."""

    status: str
    reason: str


def deterministic_extract(text: str, document_id: str, chunk_id: str) -> ExtractionResult:
    """Extract predictable entities and relations from fixture-style text."""

    entities: list[ExtractedEntity] = []
    relations: list[ExtractedRelation] = []
    entity_by_name: dict[str, ExtractedEntity] = {}

    def entity_for(
        name: str,
        entity_type: str = "concept",
        *,
        mention: bool = True,
    ) -> ExtractedEntity:
        normalized = normalize_entity_name(name)
        existing = entity_by_name.get(normalized)
        if existing is not None:
            return existing
        metadata = {"document_id": document_id, "chunk_id": chunk_id}
        if not mention:
            metadata["mention"] = "false"
        entity = ExtractedEntity(
            entity_type=entity_type,
            name=name.strip(),
            metadata=metadata,
        )
        entity_by_name[normalized] = entity
        entities.append(entity)
        return entity

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        label, value = [part.strip() for part in line.split(":", 1)]
        label_key = label.casefold()
        if label_key in _ENTITY_LABELS:
            entity_for(value, _ENTITY_LABELS[label_key])
            continue
        if label_key == "depends on" and "->" in value:
            source_name, target_name = [part.strip() for part in value.split("->", 1)]
            relations.append(
                ExtractedRelation(
                    relation_type="depends_on",
                    source=entity_for(source_name, "system", mention=False),
                    target=entity_for(target_name, "system", mention=False),
                    evidence_text=line,
                    document_id=document_id,
                    chunk_id=chunk_id,
                )
            )
            continue
        if label_key == "defines" and "->" in value:
            source_name, target_name = [part.strip() for part in value.split("->", 1)]
            relations.append(
                ExtractedRelation(
                    relation_type="defines",
                    source=entity_for(source_name, "term", mention=False),
                    target=entity_for(target_name, "concept", mention=False),
                    evidence_text=line,
                    document_id=document_id,
                    chunk_id=chunk_id,
                )
            )
            continue
        if label_key == "conflict" and " conflicts with " in value.casefold():
            source_name, target_name = _split_conflict(value)
            relations.append(
                ExtractedRelation(
                    relation_type="conflicts_with",
                    source=entity_for(source_name, "system", mention=False),
                    target=entity_for(target_name, "system", mention=False),
                    evidence_text=line,
                    document_id=document_id,
                    chunk_id=chunk_id,
                )
            )

    return ExtractionResult(entities=entities, relations=relations)


async def run_entity_extraction(
    tenant_id: str,
    kb_id: str,
    document_id: str | None = None,
    extractor: str = "deterministic",
) -> KnowledgeExtractionRun:
    """Run explicit entity extraction for one document or a whole knowledge base."""

    if extractor != "deterministic":
        raise ValueError(f"unsupported entity extractor: {extractor}")

    from fleetent.intelligence.knowledge_base import runtime
    from fleetent.intelligence.knowledge_base.extraction_store import KnowledgeEntityStore
    from fleetent.intelligence.knowledge_base.store import KnowledgeStore

    database = runtime._database()
    store = KnowledgeEntityStore(database)
    knowledge_store = KnowledgeStore(database)
    run = store.insert_run(
        tenant_id=tenant_id,
        kb_id=kb_id,
        document_id=document_id,
        extractor=extractor,
    )
    if document_id is not None:
        chunks = [
            chunk
            for chunk in knowledge_store.get_document_chunks(document_id)
            if chunk.tenant_id == tenant_id and chunk.kb_id == kb_id
        ]
        documents = {document_id: chunks} if chunks else {}
    else:
        all_chunks = knowledge_store.iter_indexable_chunks(tenant_id, kb_id)
        documents = {
            doc_id: list(grouped)
            for doc_id, grouped in groupby(all_chunks, key=lambda chunk: chunk.document_id)
        }

    documents_scanned = len(documents)
    chunks_scanned = 0
    entities_upserted = 0
    mentions_written = 0
    relations_written = 0
    failed_count = 0
    errors: list[str] = []

    for current_document_id, chunks in documents.items():
        try:
            document_entities: list[ExtractedEntity] = []
            document_relations: list[ExtractedRelation] = []
            for chunk in chunks:
                chunks_scanned += 1
                result = deterministic_extract(
                    chunk.content,
                    document_id=current_document_id,
                    chunk_id=chunk.id,
                )
                document_entities.extend(result.entities)
                document_relations.extend(result.relations)
            upserted, mentions, relations = store.replace_document_evidence(
                tenant_id=tenant_id,
                kb_id=kb_id,
                document_id=current_document_id,
                run_id=run.id,
                entities=document_entities,
                relations=document_relations,
            )
            entities_upserted += upserted
            mentions_written += mentions
            relations_written += relations
        except Exception as exc:
            failed_count += 1
            errors.append(_sanitize_error(exc))

    if failed_count and document_id is not None:
        status = "failed"
    elif failed_count:
        status = "partial_failed"
    else:
        status = "succeeded"
    return store.finish_run(
        run.id,
        status=status,
        documents_scanned=documents_scanned,
        chunks_scanned=chunks_scanned,
        entities_upserted=entities_upserted,
        mentions_written=mentions_written,
        relations_written=relations_written,
        failed_count=failed_count,
        error_summary="; ".join(errors) if errors else None,
    )


def real_llm_extraction_smoke() -> ExtractionSmokeResult:
    """Return skip status unless real LLM smoke is explicitly enabled."""

    if os.getenv("FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM") != "1":
        return ExtractionSmokeResult(
            status="skipped",
            reason="set FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM=1 to enable real LLM smoke",
        )
    return ExtractionSmokeResult(
        status="skipped",
        reason="provider config is required for real LLM entity extraction smoke",
    )


def normalize_entity_name(name: str) -> str:
    """Normalize entity names for tenant + KB scoped dedupe."""

    return _WHITESPACE_RE.sub(" ", name.strip()).casefold()


def validate_entity_type(entity_type: str) -> str:
    """Validate a first-version entity type."""

    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise ValueError(f"unsupported entity type: {entity_type}")
    return entity_type


def validate_relation_type(relation_type: str) -> str:
    """Validate a first-version relation type."""

    if relation_type not in SUPPORTED_RELATION_TYPES:
        raise ValueError(f"unsupported relation type: {relation_type}")
    return relation_type


def _split_conflict(value: str) -> tuple[str, str]:
    marker = " conflicts with "
    index = value.casefold().index(marker)
    return value[:index].strip(), value[index + len(marker) :].strip()


def _sanitize_error(exc: Exception) -> str:
    return type(exc).__name__
