import json
import re
import time
from dataclasses import dataclass, field
from typing import Literal

from fleetent.db import SQLiteDatabase
from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeReadable
from fleetent.knowledge_base.core.store import KnowledgeStore
from fleetent.observability import KBRetrievalAuditContext, record_kb_retrieval
from fleetent.structured_logging import get_logger

_NON_ALPHA_NUM_RE = re.compile(r"[^a-zA-Z0-9\u4e00-\u9fff]+")
_logger = get_logger("knowledge_base")


def _normalize_entity_name(name: str) -> str:
    return _NON_ALPHA_NUM_RE.sub(" ", name.strip()).casefold()


GraphSearchReason = Literal[
    "direct_entity_match",
    "relation_evidence",
    "related_entity_mention",
]


@dataclass(frozen=True)
class EntityRef:
    """Entity reference returned as graph search evidence."""

    id: str
    entity_type: str
    name: str
    normalized_name: str


@dataclass(frozen=True)
class RelationRef:
    """Relation reference returned as graph search evidence."""

    id: str
    relation_type: str
    source_entity_id: str
    target_entity_id: str
    evidence_chunk_id: str


@dataclass(frozen=True)
class GraphSearchChunk:
    """Knowledge chunk plus graph evidence and deterministic graph score."""

    chunk: KnowledgeChunk
    graph_score: float
    reason: GraphSearchReason
    matched_entities: list[EntityRef] = field(default_factory=list)
    relations: list[RelationRef] = field(default_factory=list)
    evidence_chunk_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphSearchResult:
    """Graph search response for one query and KB scope."""

    query: str
    tenant_id: str
    kb_ids: list[str]
    depth: int
    chunks: list[GraphSearchChunk]


async def graph_search(
    query: str,
    tenant_id: str | None = None,
    kb_ids: list[str] | None = None,
    limit: int = 10,
    depth: int = 1,
    store: KnowledgeReadable | None = None,
    audit_context: KBRetrievalAuditContext | None = None,
) -> GraphSearchResult:
    """Search knowledge chunks using extracted entity graph evidence."""

    if depth not in {0, 1}:
        raise ValueError(f"unsupported graph search depth: {depth}")

    from fleetent.knowledge_base.retrieval._settings import kb_config

    settings = kb_config()
    resolved_tenant_id = tenant_id or settings.default_tenant_id
    resolved_kb_ids = kb_ids or [settings.default_kb_id]
    if limit <= 0:
        return GraphSearchResult(
            query=query,
            tenant_id=resolved_tenant_id,
            kb_ids=resolved_kb_ids,
            depth=depth,
            chunks=[],
        )

    start = time.monotonic()
    database = _database()
    matched_entities = match_entities(database, query, resolved_tenant_id, resolved_kb_ids)
    if not matched_entities:
        result = GraphSearchResult(
            query=query,
            tenant_id=resolved_tenant_id,
            kb_ids=resolved_kb_ids,
            depth=depth,
            chunks=[],
        )
        _record_graph_search_audit(
            audit_context,
            query=query,
            result=result,
            latency_ms=(time.monotonic() - start) * 1000.0,
        )
        return result

    resolved_store = store or KnowledgeStore(database)
    candidates: dict[str, GraphSearchChunk] = {}
    matched_by_id = {entity.id: entity for entity in matched_entities}
    chunk_ids = _direct_mention_chunk_ids(
        database, resolved_tenant_id, resolved_kb_ids, matched_by_id
    )
    chunks = {
        chunk.id: chunk for chunk in resolved_store.get_chunks_by_ids(resolved_tenant_id, chunk_ids)
    }
    for chunk_id in chunk_ids:
        chunk = chunks.get(chunk_id)
        if chunk is None:
            continue
        _add_candidate(
            candidates,
            chunk,
            score=1.0,
            reason="direct_entity_match",
            entities=list(matched_entities),
            relations=[],
            evidence_chunk_ids=[chunk_id],
        )

    if depth == 1:
        relations = _relations_for_entities(
            database,
            resolved_tenant_id,
            resolved_kb_ids,
            set(matched_by_id),
        )
        relation_chunk_ids = [relation.evidence_chunk_id for relation in relations]
        relation_chunks = {
            chunk.id: chunk
            for chunk in resolved_store.get_chunks_by_ids(resolved_tenant_id, relation_chunk_ids)
        }
        for relation in relations:
            chunk = relation_chunks.get(relation.evidence_chunk_id)
            if chunk is None:
                continue
            _add_candidate(
                candidates,
                chunk,
                score=0.8,
                reason="relation_evidence",
                entities=list(matched_entities),
                relations=[relation],
                evidence_chunk_ids=[relation.evidence_chunk_id],
            )

        related_entity_ids = _related_entity_ids(relations, set(matched_by_id))
        related_entities = _entities_by_id(database, related_entity_ids)
        related_chunk_ids = _direct_mention_chunk_ids(
            database,
            resolved_tenant_id,
            resolved_kb_ids,
            related_entities,
        )
        related_chunks = {
            chunk.id: chunk
            for chunk in resolved_store.get_chunks_by_ids(resolved_tenant_id, related_chunk_ids)
        }
        for chunk_id in related_chunk_ids:
            chunk = related_chunks.get(chunk_id)
            if chunk is None:
                continue
            _add_candidate(
                candidates,
                chunk,
                score=0.6,
                reason="related_entity_mention",
                entities=list(related_entities.values()),
                relations=[],
                evidence_chunk_ids=[chunk_id],
            )

    sorted_chunks = sorted(
        candidates.values(),
        key=lambda item: (-item.graph_score, item.chunk.position, item.chunk.id),
    )[:limit]
    result = GraphSearchResult(
        query=query,
        tenant_id=resolved_tenant_id,
        kb_ids=resolved_kb_ids,
        depth=depth,
        chunks=sorted_chunks,
    )
    _record_graph_search_audit(
        audit_context,
        query=query,
        result=result,
        latency_ms=(time.monotonic() - start) * 1000.0,
    )
    return result


def _record_graph_search_audit(
    audit_context: KBRetrievalAuditContext | None,
    *,
    query: str,
    result: GraphSearchResult,
    latency_ms: float,
) -> None:
    if audit_context is None:
        return
    try:
        record_kb_retrieval(
            audit_context,
            query=query,
            results=[item.chunk for item in result.chunks],
            latency_ms=latency_ms,
            mode="graph",
            kb_ids=result.kb_ids,
            plaintext=_audit_plaintext_enabled(),
        )
    except Exception as exc:  # noqa: BLE001 — side channel; never break retrieval
        _logger.warn(
            "kb_graph_retrieval_audit_failed",
            run_id=audit_context.run_id,
            error=str(exc),
        )


def _audit_plaintext_enabled() -> bool:
    from fleetent import agent_config
    from fleetent.knowledge_base.retrieval._settings import kb_config

    audit = getattr(agent_config.active_agent_or_default().knowledge, "retrieval_audit", None)
    if audit is not None and hasattr(audit, "plaintext"):
        return bool(audit.plaintext)
    return bool(kb_config().retrieval_audit.plaintext)


def _database() -> SQLiteDatabase:
    from fleetent.knowledge_base import runtime

    return runtime._database()


def match_entities(
    database: SQLiteDatabase,
    query: str,
    tenant_id: str,
    kb_ids: list[str],
) -> list[EntityRef]:
    """Match query text to scoped entities by normalized name or aliases."""

    if not kb_ids:
        return []
    placeholders = ", ".join(f":kb_id_{index}" for index in range(len(kb_ids)))
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        **{f"kb_id_{index}": kb_id for index, kb_id in enumerate(kb_ids)},
    }
    rows = database.execute(
        f"""
        SELECT id, entity_type, name, normalized_name, metadata_json
        FROM kb_entities
        WHERE tenant_id = :tenant_id
          AND kb_id IN ({placeholders})
        ORDER BY entity_type ASC, normalized_name ASC, id ASC
        """,
        params,
    ).fetchall()
    normalized_query = _normalize_entity_name(query)
    matches: list[EntityRef] = []
    for row in rows:
        names = [str(row["normalized_name"])]
        names.extend(_metadata_aliases(str(row["metadata_json"])))
        if any(name and name in normalized_query for name in names):
            matches.append(
                EntityRef(
                    id=str(row["id"]),
                    entity_type=str(row["entity_type"]),
                    name=str(row["name"]),
                    normalized_name=str(row["normalized_name"]),
                )
            )
    return matches


def _metadata_aliases(metadata_json: str) -> list[str]:
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(metadata, dict):
        return []
    aliases = metadata.get("aliases")
    if isinstance(aliases, str):
        return [_normalize_entity_name(alias) for alias in aliases.split(",")]
    if isinstance(aliases, list):
        return [_normalize_entity_name(str(alias)) for alias in aliases]
    return []


def _direct_mention_chunk_ids(
    database: SQLiteDatabase,
    tenant_id: str,
    kb_ids: list[str],
    entities_by_id: dict[str, EntityRef],
) -> list[str]:
    if not entities_by_id:
        return []
    entity_placeholders = ", ".join(f":entity_id_{index}" for index in range(len(entities_by_id)))
    kb_placeholders = ", ".join(f":kb_id_{index}" for index in range(len(kb_ids)))
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        **{f"entity_id_{index}": entity_id for index, entity_id in enumerate(entities_by_id)},
        **{f"kb_id_{index}": kb_id for index, kb_id in enumerate(kb_ids)},
    }
    rows = database.execute(
        f"""
        SELECT DISTINCT chunk_id
        FROM kb_entity_mentions
        WHERE tenant_id = :tenant_id
          AND kb_id IN ({kb_placeholders})
          AND entity_id IN ({entity_placeholders})
        ORDER BY chunk_id ASC
        """,
        params,
    ).fetchall()
    return [str(row["chunk_id"]) for row in rows]


def _relations_for_entities(
    database: SQLiteDatabase,
    tenant_id: str,
    kb_ids: list[str],
    entity_ids: set[str],
) -> list[RelationRef]:
    if not entity_ids:
        return []
    entity_placeholders = ", ".join(f":entity_id_{index}" for index in range(len(entity_ids)))
    kb_placeholders = ", ".join(f":kb_id_{index}" for index in range(len(kb_ids)))
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        **{f"entity_id_{index}": entity_id for index, entity_id in enumerate(entity_ids)},
        **{f"kb_id_{index}": kb_id for index, kb_id in enumerate(kb_ids)},
    }
    rows = database.execute(
        f"""
        SELECT id, relation_type, source_entity_id, target_entity_id, evidence_chunk_id
        FROM kb_relations
        WHERE tenant_id = :tenant_id
          AND kb_id IN ({kb_placeholders})
          AND (
            source_entity_id IN ({entity_placeholders})
            OR target_entity_id IN ({entity_placeholders})
          )
        ORDER BY id ASC
        """,
        params,
    ).fetchall()
    return [
        RelationRef(
            id=str(row["id"]),
            relation_type=str(row["relation_type"]),
            source_entity_id=str(row["source_entity_id"]),
            target_entity_id=str(row["target_entity_id"]),
            evidence_chunk_id=str(row["evidence_chunk_id"]),
        )
        for row in rows
    ]


def _related_entity_ids(relations: list[RelationRef], matched_entity_ids: set[str]) -> set[str]:
    related: set[str] = set()
    for relation in relations:
        if relation.relation_type == "mentions":
            continue
        if relation.relation_type in {"related_to", "conflicts_with"}:
            if relation.source_entity_id in matched_entity_ids:
                related.add(relation.target_entity_id)
            if relation.target_entity_id in matched_entity_ids:
                related.add(relation.source_entity_id)
            continue
        if relation.source_entity_id in matched_entity_ids:
            related.add(relation.target_entity_id)
    return related - matched_entity_ids


def _entities_by_id(database: SQLiteDatabase, entity_ids: set[str]) -> dict[str, EntityRef]:
    if not entity_ids:
        return {}
    placeholders = ", ".join(f":entity_id_{index}" for index in range(len(entity_ids)))
    rows = database.execute(
        f"""
        SELECT id, entity_type, name, normalized_name
        FROM kb_entities
        WHERE id IN ({placeholders})
        ORDER BY entity_type ASC, normalized_name ASC, id ASC
        """,
        {f"entity_id_{index}": entity_id for index, entity_id in enumerate(entity_ids)},
    ).fetchall()
    return {
        str(row["id"]): EntityRef(
            id=str(row["id"]),
            entity_type=str(row["entity_type"]),
            name=str(row["name"]),
            normalized_name=str(row["normalized_name"]),
        )
        for row in rows
    }


def _add_candidate(
    candidates: dict[str, GraphSearchChunk],
    chunk: KnowledgeChunk,
    *,
    score: float,
    reason: GraphSearchReason,
    entities: list[EntityRef],
    relations: list[RelationRef],
    evidence_chunk_ids: list[str],
) -> None:
    existing = candidates.get(chunk.id)
    if existing is None:
        candidates[chunk.id] = GraphSearchChunk(
            chunk=chunk,
            graph_score=score,
            reason=reason,
            matched_entities=_dedupe_entities(entities),
            relations=_dedupe_relations(relations),
            evidence_chunk_ids=sorted(set(evidence_chunk_ids)),
        )
        return
    candidates[chunk.id] = GraphSearchChunk(
        chunk=chunk,
        graph_score=max(existing.graph_score, score),
        reason=existing.reason if existing.graph_score >= score else reason,
        matched_entities=_dedupe_entities([*existing.matched_entities, *entities]),
        relations=_dedupe_relations([*existing.relations, *relations]),
        evidence_chunk_ids=sorted({*existing.evidence_chunk_ids, *evidence_chunk_ids}),
    )


def _dedupe_entities(entities: list[EntityRef]) -> list[EntityRef]:
    return list({entity.id: entity for entity in entities}.values())


def _dedupe_relations(relations: list[RelationRef]) -> list[RelationRef]:
    return list({relation.id: relation for relation in relations}.values())
