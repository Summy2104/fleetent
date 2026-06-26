"""Write pipeline for user memory facts: extract → resolve → classify → commit.

This module is deliberately store-agnostic at the function boundary: each
public function takes a ``store`` (the facts_store module or a stand-in) and an
``llm_client`` so it can be unit-tested without a real DB or model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import struct
from datetime import UTC, datetime
from typing import Any, Protocol

from fleetent.memory.facts_models import (
    FORGET_RELATION,
    RENAME_RELATION,
    Cardinality,
    ClassifiedFact,
    ClassifyVerdict,
    Fact,
    RawFact,
    RelationCluster,
    ResolvedFact,
)
from fleetent.structured_logging import get_logger
from fleetent.vector_store.runtime import embed_text

logger = logging.getLogger(__name__)
# Structured logger for pipeline observability (what was extracted, how it
# resolved/classified, what got committed) — so "why wasn't this stored?" is
# answerable from logs instead of by inspecting the DB.
slog = get_logger("memory.facts_pipeline")

# Cosine threshold for merging a raw relation into an existing wordlist entry.
RELATION_MERGE_THRESHOLD = 0.90

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

EXTRACT_SYSTEM = (
    "Extract durable facts from the conversation as (subject, relation, object) "
    "triples. Return a JSON array. Each item: "
    '{"subject": str, "relation": str, "object": str, "temporal": str, '
    '"statement": str}. '
    "statement is ONE concise natural-language sentence stating the fact with an "
    "EXPLICIT subject, in the conversation's language — so a reader knows exactly "
    "who it is about. E.g. subject='user',relation='name',object='Xin' → "
    "statement='用户的名字是 Xin'. subject='agent',relation='tone',object='简洁' → "
    "statement='用户希望助手回答简洁'. subject='张三' → statement='用户的老板叫张三'. "
    "subject identifies WHO the fact is about. Use the EXACT lowercase literal "
    "'user' for facts about the human user themselves (never translate it to 用户/我), "
    "and the EXACT literal 'agent' for facts about the assistant/you (never 助手/你) "
    '— e.g. the user says "你叫小派" / "记住你叫 X" → subject=\'agent\', '
    "relation='name'. For a named third party the user mentions, use that person's "
    "name as subject (e.g. \"我老板叫张三\" → subject='张三'). When unsure, default "
    "to 'user'. "
    "relation is a SHORT, GENERIC snake_case predicate (1-3 words): the KIND of fact, "
    "never the value. The specific value goes in object. "
    "Good: relation='located_in', object='Shanghai'. "
    "Good: relation='years_of_experience', object='8'. "
    "Bad: relation='current_work_city' (too specific — use located_in). "
    "Bad: relation='has_software_dev_experience_years' (folds the value in — use "
    "years_of_experience). "
    "Bad: relation='builds_enterprise_ai_platform' (a whole sentence — use "
    "works_on_project with object='enterprise AI platform'). "
    "For the user's name or how they want to be addressed, ALWAYS use "
    "relation='name' (object = the name), never knows_as / called / nickname. "
    "For a PROGRAMMING LANGUAGE the user likes/uses, ALWAYS use "
    "relation='prefers_language' (object = the language), never prefers_tool — "
    "reserve prefers_tool for non-language tools (editors, frameworks, CLIs). "
    "For a SKILL or thing the user knows how to do, use relation='has_skill' with "
    "object = a SHORT canonical skill NAME (e.g. object='Slack @-mention'), NOT a "
    "boolean/restatement. Never fold the skill into the relation "
    "(no knows_how_to_at_mention) and never use object='true'/'yes'. State the same "
    "skill the SAME way each time so it is not stored as a near-duplicate. "
    "If the user CORRECTS or RENAMES an entity — '张三实际叫张洋' / '把张三改成张洋' / "
    "'修正：X 应该是 Y' — emit a single triple subject=<old name>, "
    "relation='renamed_to', object=<new name> (e.g. subject='张三', "
    "relation='renamed_to', object='张洋'). Do not also emit the entity's other "
    "facts in that turn; the rename moves them automatically. "
    "If the user asks to FORGET or DELETE a memory — '忘记我喜欢 Python' / "
    "'删掉张三' / 'forget that I...' — emit relation='forget': to drop one fact use "
    "subject=<who> object=<the value to forget> (e.g. subject='user', "
    "relation='forget', object='Python'); to drop everything about an entity set "
    "object to that entity's name (e.g. subject='张三', relation='forget', "
    "object='张三'). "
    "renamed_to and forget are MUTUALLY EXCLUSIVE: a delete/forget request emits "
    "ONLY 'forget' (never also 'renamed_to'); a rename emits ONLY 'renamed_to'. "
    "Emit at most one directive per entity per turn. "
    "temporal classifies WHEN THE FACT STOPS BEING USEFUL — pick exactly one of: "
    "'today', 'tomorrow', 'this_week', 'this_month', 'none'. "
    "Do NOT output any date or time yourself; just the label. The exact expiry is "
    "computed in code. Rules:\n"
    "  - A one-off event tied to a day (ate/met/went/had a meeting) → the label "
    "for THAT day. E.g. '今天早上吃了薄饼' / '昨天见了客户' → 'today'. "
    "(There is no 'yesterday'; for a past day use 'today' so it expires by today's end.)\n"
    "  - A future deadline/window → its label. E.g. '这周内交报告' → 'this_week'.\n"
    "  - An ongoing or durable state → 'none'. E.g. '最近一周在开发X' "
    "(project still in progress), '我做了3年后端', '我住在上海' — a mentioned "
    "time span does NOT make these expire.\n"
    "When unsure between an event and a state: a single completed action on a day "
    "is an event (use a day label); a persisting situation is 'none'. "
    "Only extract explicit, persistent facts ABOUT people. "
    "DO NOT extract task/command/request intents — '提醒我做X' / '帮我...' / "
    "'请你...' / 'remind me to...' are to-dos or instructions, NOT facts; skip "
    "them entirely (they are handled elsewhere as scheduled tasks). "
    "DO NOT INVENT or INFER facts that were not stated: if the user says "
    "'提醒我测试记忆系统', that does NOT mean they are a 'designer' or that "
    "'测试记忆系统' is their project — extract nothing unless the fact is "
    "explicitly asserted. "
    "DO NOT extract REAL-TIME or SYSTEM/META information — the assistant's own "
    "tool count/capabilities/config, counts/status from this conversation, or "
    "anything queried live and subject to change (e.g. '你有11个工具' → do NOT "
    "store count=11 / has_tool_count=11). These are not durable facts about a "
    "person. "
    "Also skip questions and hypotheticals. Return [] when there is nothing to "
    "remember."
)

_REUSE_INSTRUCTION = (
    "\n\nReuse one of these existing relations ONLY when it has the SAME MEANING as "
    "the fact. If none matches the meaning, INVENT a new accurate snake_case "
    "relation — never bend the meaning just to reuse one. "
    "E.g. 'ate pancakes this morning' is an eating event, not a preference: use "
    "relation='ate' (or 'had_meal'), NOT 'likes'. Reserve 'likes' for stated "
    "preferences ('I like pancakes'). The relation and your statement MUST agree: "
    "if the statement says 'ate', the relation cannot be 'likes'. "
    "Existing relations:\n{relations}"
)


def _extract_system_prompt(known_relations: list[str] | None) -> str:
    if not known_relations:
        return EXTRACT_SYSTEM
    listed = ", ".join(sorted(known_relations))
    return EXTRACT_SYSTEM + _REUSE_INSTRUCTION.format(relations=listed)


_VERDICTS: frozenset[str] = frozenset(
    {"Equivalent", "Contradict", "NewSubsumed", "Subsumes", "Orthogonal"}
)


async def run_pipeline(
    *,
    user_id: str,
    turn_content: str,
    db: Any,
    vector_backend: Any,
    llm_client: Any,
    source_turn: str | None,
) -> None:
    """Run the full write pipeline for one conversation turn.

    extract → resolve (per fact) → classify (concurrent, per fact) → commit
    (single transaction) → vector sync (best-effort).  No-ops when extraction
    finds nothing.
    """
    store = _relation_store()
    known = [c.relation for c in store.list_relation_clusters()]
    # Names the user is already known by, so the LLM using the user's own name as a
    # subject ("Xin works_at …") folds back to 'user' instead of duplicating them.
    user_aliases = _known_user_aliases(user_id)
    raws = await extract_facts(
        turn_content, llm_client, known_relations=known, user_aliases=user_aliases
    )
    slog.info(
        "facts_extracted",
        user_id=user_id,
        source_turn=source_turn,
        count=len(raws),
        triples=[f"{r.subject}|{r.relation}={r.object}" for r in raws],
    )
    if not raws:
        # Make "nothing was stored" explicit and distinguishable from a crash.
        slog.info("facts_pipeline_noop", user_id=user_id, reason="no_facts_extracted")
        return

    resolved = [await resolve_relation(raw, store, llm_client) for raw in raws]

    classified = list(
        await asyncio.gather(
            *(
                classify_relation(
                    r,
                    _active_facts_for_relation(user_id, r.subject, r.relation),
                    llm_client,
                )
                for r in resolved
            )
        )
    )
    slog.info(
        "facts_classified",
        user_id=user_id,
        verdicts=[f"{c.subject}|{c.relation}={c.object}:{c.verdict}" for c in classified],
    )

    new_active = _commit_facts(user_id, classified, db, source_turn=source_turn)
    superseded_ids: list[str] = []
    await _sync_vectors(
        user_id,
        new_active=new_active,
        superseded_ids=superseded_ids,
        vector_backend=vector_backend,
    )
    slog.info(
        "facts_committed",
        user_id=user_id,
        committed=[
            f"{f.subject}|{f.relation}={f.object}"
            f"(expires={'never' if f.expires_at is None else f.expires_at.isoformat()})"
            for f in new_active
        ],
        committed_count=len(new_active),
    )


async def run_pipeline_from_conversation(
    user_id: str,
    conversation: list[dict[str, Any]],
    *,
    model_policy: Any = None,
    source_turn: str | None = None,
) -> None:
    """Adapter from the runtime's (conversation, policy) shape to run_pipeline.

    Builds the turn text, resolves the model client, and pulls the injected DB +
    vector backend.  Best-effort: any setup failure (no model configured, DB not
    wired) is logged and swallowed — memory write is auxiliary to the reply.
    """
    try:
        db, vector_backend = _facts_db_and_backend()
        llm_client = _build_llm_client(model_policy)
    except Exception:
        logger.warning("facts_pipeline: pipeline setup failed — skipping", exc_info=True)
        return

    turn_content = _conversation_to_text(conversation)
    await run_pipeline(
        user_id=user_id,
        turn_content=turn_content,
        db=db,
        vector_backend=vector_backend,
        llm_client=llm_client,
        source_turn=source_turn,
    )


def _conversation_to_text(conversation: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in conversation:
        role = message.get("role", "")
        content = message.get("content", "")
        if isinstance(content, str) and content.strip():
            parts.append(f"{role}: {content.strip()}")
    return "\n".join(parts)


def _facts_db_and_backend() -> tuple[Any, Any]:
    from fleetent.memory import facts_store

    return facts_store._facts_database(), facts_store._facts_vector_backend


def _build_llm_client(model_policy: Any) -> Any:
    """Resolve an AsyncOpenAI client for the memory_extraction route."""
    from openai import AsyncOpenAI

    from fleetent import agent_config
    from fleetent.model import ModelConfigError, ModelPolicySnapshot

    policy = model_policy or ModelPolicySnapshot.from_agent(agent_config.active_agent_or_default())
    cfg = policy.resolve("memory_extraction")[0]
    if cfg.protocol != "openai_chat" or not cfg.base_url or not cfg.model:
        raise ModelConfigError("memory_extraction route must target an openai_chat model")
    client = AsyncOpenAI(base_url=cfg.base_url, api_key=policy.require_api_key(cfg) or "fleetent")
    # extract_facts / classify_relation read this attribute for the model name.
    client._fleetent_model = cfg.model  # type: ignore[attr-defined]
    return client


# Indirection seams — kept as module-level functions so run_pipeline can be unit
# tested by monkeypatching them without a real DB or vector backend.


def _relation_store() -> _RelationStore:
    from fleetent.memory import facts_store

    return facts_store  # type: ignore[return-value]


def _active_facts_for_relation(user_id: str, subject: str, relation: str) -> list[Fact]:
    from fleetent.memory import facts_store

    return facts_store.active_facts_for_relation(user_id, subject, relation)


def _known_user_aliases(user_id: str) -> set[str]:
    """Casefolded names the user is known by — their active (user, name, *) facts."""
    from fleetent.memory import facts_store

    names = facts_store.active_facts_for_relation(user_id, "user", "name")
    return {f.object.casefold() for f in names}


def _commit_facts(
    user_id: str, classified: list[Any], db: Any, *, source_turn: str | None
) -> list[Fact]:
    from fleetent.memory import facts_commit

    return facts_commit.commit_facts(user_id, classified, db, source_turn=source_turn)


async def _sync_vectors(
    user_id: str, *, new_active: list[Fact], superseded_ids: list[str], vector_backend: Any
) -> None:
    from fleetent.memory import facts_commit

    await facts_commit.sync_vectors(
        user_id,
        new_active=new_active,
        superseded_ids=superseded_ids,
        vector_backend=vector_backend,
    )


async def extract_facts(
    turn_content: str,
    llm_client: Any,
    known_relations: list[str] | None = None,
    user_aliases: set[str] | None = None,
) -> list[RawFact]:
    """Extract raw (subject, relation, object) triples from a conversation turn.

    When ``known_relations`` is given, the existing relation wordlist is surfaced
    in the prompt so the LLM reuses canonical predicates instead of minting a new
    one per sentence (the wordlist-fragmentation failure mode, design risk R2).

    ``user_aliases`` is the set of casefolded names the user is known by (from
    prior name facts); a subject matching one is folded back to 'user' so the
    same person is not split into 'user' vs their own name.

    Malformed entries are skipped with a warning; unparseable LLM output yields
    an empty list.  No DB or vector access here — pure extraction.
    """
    if llm_client is None:
        return []
    system_prompt = _extract_system_prompt(known_relations)
    try:
        create_completion = llm_client.chat.completions.create
        response = await create_completion(
            model=getattr(llm_client, "_fleetent_model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": turn_content},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
    except Exception:
        logger.warning("facts_pipeline: extract_facts LLM call failed", exc_info=True)
        return []

    parsed = _parse_json_array(content)
    facts: list[RawFact] = []
    for entry in parsed:
        raw = _entry_to_raw_fact(entry, user_aliases=user_aliases)
        if raw is None:
            logger.warning("facts_pipeline: skipping malformed extracted fact %r", entry)
            continue
        facts.append(raw)
    return facts


def _parse_json_array(content: str) -> list[Any]:
    text = content.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("facts_pipeline: extract_facts output is not valid JSON")
        return []
    return parsed if isinstance(parsed, list) else []


def _entry_to_raw_fact(entry: Any, user_aliases: set[str] | None = None) -> RawFact | None:
    if not isinstance(entry, dict):
        return None
    subject = entry.get("subject")
    relation = entry.get("relation")
    obj = entry.get("object")
    if not (isinstance(subject, str) and isinstance(relation, str) and isinstance(obj, str)):
        return None
    if not (subject.strip() and relation.strip() and obj.strip()):
        return None
    temporal = entry.get("temporal")
    temporal = temporal.strip() if isinstance(temporal, str) and temporal.strip() else "none"
    statement = entry.get("statement")
    statement = statement.strip() if isinstance(statement, str) and statement.strip() else None
    return RawFact(
        subject=_canonical_subject(subject.strip(), user_aliases),
        relation=relation.strip(),
        object=obj.strip(),
        temporal=temporal,
        statement=statement,
    )


# The user and the agent are reserved subjects with fixed canonical tokens. The
# LLM drifts between languages/pronouns (用户/我/me, 助手/你/assistant), which would
# split one subject into duplicates; map all aliases back deterministically.
_USER_ALIASES: frozenset[str] = frozenset({"user", "用户", "我", "me", "i", "myself"})
_AGENT_ALIASES: frozenset[str] = frozenset(
    {"agent", "assistant", "助手", "你", "bot", "ai", "ai助手"}
)


def _canonical_subject(subject: str, user_aliases: set[str] | None = None) -> str:
    """Map user/agent aliases to canonical 'user'/'agent'; keep named parties as-is.

    ``user_aliases`` (casefolded) are names the user is known by — e.g. their own
    name 'Xin' — which the LLM sometimes uses as a subject for the user themselves;
    those fold back to 'user' too.
    """
    low = subject.casefold()
    if low in _USER_ALIASES or (user_aliases is not None and low in user_aliases):
        return "user"
    if low in _AGENT_ALIASES:
        return "agent"
    return subject


class _RelationStore(Protocol):
    """The subset of facts_store used during relation resolution."""

    def list_relation_clusters(self) -> list[RelationCluster]: ...

    def get_relation_cluster(self, relation: str) -> RelationCluster | None: ...

    def insert_relation_cluster(self, cluster: RelationCluster) -> None: ...

    def set_relation_cluster_embedding(self, relation: str, embedding: bytes) -> None: ...


async def resolve_relation(
    raw: RawFact,
    store: _RelationStore,
    llm_client: Any,
) -> ResolvedFact:
    """Normalize raw.relation to a relation_clusters entry, creating one if needed.

    Computes the embedding for ``raw.relation`` and finds the most similar existing
    cluster.  If cosine >= RELATION_MERGE_THRESHOLD, merges into it (inheriting its
    cardinality); otherwise creates a new cluster with LLM-judged cardinality.
    """
    if raw.relation in (RENAME_RELATION, FORGET_RELATION):
        # Directives (rename / forget) pass through untouched: not real relations,
        # never merged into the wordlist, handled at commit time.
        return ResolvedFact(
            subject=raw.subject,
            relation=raw.relation,
            object=raw.object,
            temporal=raw.temporal,
            cardinality="single",
            statement=raw.statement,
        )
    query_vec = await embed_text(raw.relation)
    clusters = store.list_relation_clusters()

    best_relation: str | None = None
    best_cardinality: Cardinality | None = None
    best_score = -1.0
    for cluster in clusters:
        if cluster.embedding is None:
            # Backfill the embedding lazily so future comparisons are cheap.
            cluster_vec = await embed_text(cluster.relation)
            store.set_relation_cluster_embedding(cluster.relation, _vector_to_blob(cluster_vec))
        else:
            cluster_vec = _blob_to_vector(cluster.embedding)
        score = _cosine(query_vec, cluster_vec)
        if score > best_score:
            best_score = score
            best_relation = cluster.relation
            best_cardinality = cluster.cardinality

    if (
        best_relation is not None
        and best_cardinality is not None
        and (best_score >= RELATION_MERGE_THRESHOLD)
    ):
        return ResolvedFact(
            subject=raw.subject,
            relation=best_relation,
            object=raw.object,
            temporal=raw.temporal,
            cardinality=best_cardinality,
            statement=raw.statement,
        )

    cardinality = await _judge_cardinality(raw.relation, llm_client)
    store.insert_relation_cluster(
        RelationCluster(
            relation=raw.relation,
            cardinality=cardinality,
            embedding=_vector_to_blob(query_vec),
            created_at=datetime.now(UTC).replace(microsecond=0),
        )
    )
    return ResolvedFact(
        subject=raw.subject,
        relation=raw.relation,
        object=raw.object,
        temporal=raw.temporal,
        cardinality=cardinality,
        statement=raw.statement,
    )


async def _judge_cardinality(relation: str, llm_client: Any) -> Cardinality:
    """Ask the LLM whether a new relation is single- or multi-valued.

    Defaults to 'multi' (coexistence) when the model is unavailable or its answer
    is unparseable — the conservative choice, since 'single' would silently
    supersede prior facts.
    """
    if llm_client is None:
        return "multi"
    try:
        create_completion = llm_client.chat.completions.create
        response = await create_completion(
            model=getattr(llm_client, "_fleetent_model", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Decide if a user-fact relation is single-valued or multi-valued.\n"
                        "single = the relation holds exactly one current value, so a new "
                        "value should REPLACE the old one. This includes: roles/titles, "
                        "current employer, location/city, timezone, and any quantity, "
                        "count, duration, age, level, or year (e.g. years_of_experience, "
                        "blogging_years, age, seniority) — these track one current number.\n"
                        "multi = several values naturally coexist (e.g. skills, spoken "
                        "languages, tools, interests, projects, things liked/disliked).\n"
                        "When the object is a number, duration, or 'current X', strongly "
                        "prefer single. Answer with exactly one word: single or multi."
                    ),
                },
                {"role": "user", "content": f"relation: {relation}"},
            ],
            temperature=0,
        )
        answer = response.choices[0].message.content or ""
    except Exception:
        return "multi"
    return "single" if answer.strip().lower().startswith("single") else "multi"


async def classify_relation(
    resolved: ResolvedFact,
    existing_facts: list[Fact],
    llm_client: Any,
) -> ClassifiedFact:
    """Assign a verdict comparing a resolved fact against existing active facts.

    With no existing facts the verdict is trivially Orthogonal (the new fact
    cannot conflict with anything).  Otherwise the LLM compares the new object
    against the existing objects and returns one verdict; an unparseable answer
    defaults to Orthogonal (the safe choice — it inserts without superseding).
    """
    if not existing_facts:
        return _with_verdict(resolved, "Orthogonal")

    # Deterministic short-circuit: an object identical (case/space-insensitive) to
    # an existing one is trivially Equivalent — skip the LLM so a repeated value
    # (e.g. the same agent name said twice) is never stored or superseded again.
    new_norm = _normalize_object(resolved.object)
    if any(_normalize_object(f.object) == new_norm for f in existing_facts):
        return _with_verdict(resolved, "Equivalent")

    verdict = await _judge_verdict(resolved, existing_facts, llm_client)
    return _with_verdict(resolved, verdict)


def _normalize_object(value: str) -> str:
    return " ".join(value.split()).casefold()


async def _judge_verdict(
    resolved: ResolvedFact,
    existing_facts: list[Fact],
    llm_client: Any,
) -> ClassifyVerdict:
    if llm_client is None:
        return "Orthogonal"
    old_objects = "; ".join(f.object for f in existing_facts)
    try:
        create_completion = llm_client.chat.completions.create
        response = await create_completion(
            model=getattr(llm_client, "_fleetent_model", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Compare a NEW user fact against EXISTING facts sharing the same "
                        "subject and relation. Reply with exactly one word: "
                        "Equivalent (same meaning), Contradict (mutually exclusive), "
                        "NewSubsumed (new is a subset of an existing one), "
                        "Subsumes (new is broader than an existing one), or "
                        "Orthogonal (unrelated, can coexist)."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"relation: {resolved.relation}\n"
                        f"existing objects: {old_objects}\n"
                        f"new object: {resolved.object}"
                    ),
                },
            ],
            temperature=0,
        )
        answer = (response.choices[0].message.content or "").strip()
    except Exception:
        return "Orthogonal"
    for verdict in _VERDICTS:
        if answer.lower().startswith(verdict.lower()):
            return verdict  # type: ignore[return-value]
    return "Orthogonal"


def _with_verdict(resolved: ResolvedFact, verdict: ClassifyVerdict) -> ClassifiedFact:
    return ClassifiedFact(
        subject=resolved.subject,
        relation=resolved.relation,
        object=resolved.object,
        temporal=resolved.temporal,
        cardinality=resolved.cardinality,
        verdict=verdict,
        statement=resolved.statement,
    )


# ── vector helpers ────────────────────────────────────────────────────────────


def _vector_to_blob(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _blob_to_vector(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
