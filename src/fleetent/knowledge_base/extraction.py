from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fleetent.knowledge_base.extraction_store import KnowledgeExtractionRun

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
_MODEL_POLICY_SYSTEM_PROMPT = """
Extract knowledge-graph entities and relations from one document chunk.
Return strict JSON with shape {"entities":[...],"relations":[...]}.
Each entity item must include "entity_type" and "name".
Each relation item must include "relation_type", "source", "target", and "evidence_text".
Use only supported entity types and relation types.
""".strip()


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

    if extractor not in {"deterministic", "model_policy"}:
        raise ValueError(f"unsupported entity extractor: {extractor}")

    from fleetent.knowledge_base import runtime
    from fleetent.knowledge_base.extraction_store import KnowledgeEntityStore
    from fleetent.knowledge_base.store import KnowledgeStore

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
                result = await _extract_chunk(
                    chunk.content,
                    document_id=current_document_id,
                    chunk_id=chunk.id,
                    extractor=extractor,
                )
                document_entities.extend(result.entities)
                document_relations.extend(result.relations)
            upserted, mentions, relations = store.replace_document_evidence(
                tenant_id=tenant_id,
                kb_id=kb_id,
                document_id=current_document_id,
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
        run,
        status=status,
        documents_scanned=documents_scanned,
        chunks_scanned=chunks_scanned,
        entities_upserted=entities_upserted,
        mentions_written=mentions_written,
        relations_written=relations_written,
        failed_count=failed_count,
        error_summary="; ".join(errors) if errors else None,
    )


async def _extract_chunk(
    text: str,
    *,
    document_id: str,
    chunk_id: str,
    extractor: str,
) -> ExtractionResult:
    if extractor == "deterministic":
        return deterministic_extract(text, document_id=document_id, chunk_id=chunk_id)
    return await _extract_chunk_with_model_policy(text, document_id=document_id, chunk_id=chunk_id)


def _build_model_policy_client() -> object:
    from openai import AsyncOpenAI

    from fleetent import agent_config
    from fleetent.model import ModelConfigError, ModelPolicySnapshot

    policy = ModelPolicySnapshot.from_agent(agent_config.active_agent_or_default())
    cfg = policy.resolve("kb_extraction")[0]
    if cfg.protocol != "openai_chat" or not cfg.base_url or not cfg.model:
        raise ModelConfigError("kb_extraction route must target an openai_chat model")
    client = AsyncOpenAI(base_url=cfg.base_url, api_key=policy.require_api_key(cfg) or "fleetent")
    client._fleetent_model = cfg.model  # type: ignore[attr-defined]
    return client


async def _extract_chunk_with_model_policy(
    text: str,
    *,
    document_id: str,
    chunk_id: str,
) -> ExtractionResult:
    client = _build_model_policy_client()
    create_completion = client.chat.completions.create
    response = await create_completion(
        model=getattr(client, "_fleetent_model", "default"),
        messages=[
            {"role": "system", "content": _MODEL_POLICY_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    return _parse_model_policy_result(content, document_id=document_id, chunk_id=chunk_id)


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


def _parse_model_policy_result(
    content: str, *, document_id: str, chunk_id: str
) -> ExtractionResult:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("kb extraction response must be a JSON object")
    raw_entities = payload.get("entities")
    raw_relations = payload.get("relations")
    if not isinstance(raw_entities, list) or not isinstance(raw_relations, list):
        raise ValueError("kb extraction response missing entities/relations lists")

    entities: list[ExtractedEntity] = []
    entity_by_name: dict[str, ExtractedEntity] = {}
    for entry in raw_entities:
        if not isinstance(entry, dict):
            raise ValueError("kb extraction entity must be an object")
        entity = ExtractedEntity(
            entity_type=str(entry["entity_type"]),
            name=str(entry["name"]),
            confidence=float(entry.get("confidence", 1.0)),
            metadata={"document_id": document_id, "chunk_id": chunk_id},
        )
        entities.append(entity)
        entity_by_name[entity.normalized_name] = entity

    relations: list[ExtractedRelation] = []
    for entry in raw_relations:
        if not isinstance(entry, dict):
            raise ValueError("kb extraction relation must be an object")
        source_name = normalize_entity_name(str(entry["source"]))
        target_name = normalize_entity_name(str(entry["target"]))
        source = entity_by_name.get(source_name)
        target = entity_by_name.get(target_name)
        if source is None or target is None:
            raise ValueError("kb extraction relation references unknown entity")
        relations.append(
            ExtractedRelation(
                relation_type=str(entry["relation_type"]),
                source=source,
                target=target,
                evidence_text=str(entry["evidence_text"]),
                document_id=document_id,
                chunk_id=chunk_id,
                confidence=float(entry.get("confidence", 1.0)),
            )
        )
    return ExtractionResult(entities=entities, relations=relations)
