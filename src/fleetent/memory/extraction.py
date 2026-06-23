"""LLM extraction workflow for User Memory."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from openai import AsyncOpenAI

from fleetent import vector_store
from fleetent.memory import store
from fleetent.memory.models import MemoryItem, MemoryType
from fleetent.model import ModelConfigError, ModelPolicySnapshot

EXTRACT_SYSTEM = (
    "Extract user semantic memories from the conversation. Return a JSON array of actions. "
    "Use action=create with type identity, preferences, or context and non-empty content. "
    "Use action=update with target_id, matching type, and non-empty content when the "
    "conversation corrects an existing identity, preferences, or context memory. "
    "Use action=delete with target_id when the user asks to forget an existing memory. "
    "Use action=ignore for facts that should not be remembered, including uncertain facts "
    "and one-time preferences or formatting requests."
)
VALID_TYPES = {"identity", "preferences", "context"}
CONTEXT_TTL = timedelta(days=30)
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
IDENTITY_ROLE_SUFFIXES = (
    "architect",
    "developer",
    "engineer",
    "manager",
    "operator",
    "researcher",
)


async def extract_and_update(
    user_id: str,
    conversation: list[dict[str, Any]],
    model_policy: ModelPolicySnapshot | None = None,
) -> None:
    """Extract structured memories from conversation and update the memory store."""
    from fleetent import agent_config

    snapshot = store.memory_snapshot(user_id)
    vector_ns = vector_store.memory_namespace(user_id)
    policy = model_policy or ModelPolicySnapshot.from_agent(agent_config.active_agent_or_default())
    cfg = policy.resolve("memory_extraction")[0]
    if cfg.protocol != "openai_chat" or not cfg.base_url or not cfg.model:
        raise ModelConfigError("memory_extraction route must target an openai_chat model")
    client = AsyncOpenAI(base_url=cfg.base_url, api_key=policy.require_api_key(cfg) or "fleetent")
    create_completion = cast(Any, client.chat.completions.create)
    response = await create_completion(
        model=cfg.model,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": extraction_user_message(conversation, snapshot)},
        ],
        max_tokens=cfg.max_tokens,
        **cfg.params,
    )
    actions = parse_action_array(response.choices[0].message.content or "[]")
    if actions is None:
        return

    now = datetime.now(UTC).replace(microsecond=0)
    snapshot_by_id = {item.id: item for items in snapshot.values() for item in items}
    for action in actions:
        if not isinstance(action, dict):
            continue
        if targets_non_user_memory(action):
            continue
        action_name = action.get("action")
        if action_name == "delete":
            target_id = action.get("target_id")
            target = snapshot_by_id.get(target_id) if isinstance(target_id, str) else None
            if target is None:
                continue
            store.delete_memory(user_id, target.id)
            await store.vector_backend().delete(target.id, vector_ns)
            continue
        content = action.get("content")
        raw_type = action.get("type")
        if not isinstance(content, str) or not content.strip() or raw_type not in VALID_TYPES:
            continue
        memory_type = cast(MemoryType, raw_type)
        normalized_content = normalize_action_content(memory_type, content)
        if action_name == "update":
            target_id = action.get("target_id")
            target = snapshot_by_id.get(target_id) if isinstance(target_id, str) else None
            if target is None or target.type != memory_type:
                continue
            updated = MemoryItem(
                id=target.id,
                user_id=user_id,
                type=target.type,
                content=normalized_content,
                created_at=target.created_at,
                updated_at=now,
                expires_at=expires_at(memory_type, now),
            )
            store.update_memory(updated)
            vector = await vector_store.embed_text(updated.content)
            await store.vector_backend().upsert(updated.id, vector, vector_ns)
            continue
        if action_name != "create":
            continue
        item = MemoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=memory_type,
            content=normalized_content,
            created_at=now,
            updated_at=now,
            expires_at=expires_at(memory_type, now),
        )
        store.insert_memory(item)
        vector = await vector_store.embed_text(item.content)
        await store.vector_backend().upsert(item.id, vector, vector_ns)


def strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def parse_action_array(text: str) -> list[Any] | None:
    """Return the first valid JSON array from a raw or provider-wrapped response."""
    decoder = json.JSONDecoder()
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return parsed

    for index, char in enumerate(text):
        if char != "[":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return parsed
    return None


def _json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates = [stripped, strip_markdown_fence(stripped)]
    candidates.extend(match.group(1).strip() for match in JSON_FENCE_RE.finditer(text))
    return candidates


def normalize_action_content(memory_type: MemoryType, content: str) -> str:
    """Normalize common real-provider wording to user-scoped memory content."""
    text = " ".join(content.strip().split())
    lowered = text.casefold()
    if lowered.startswith("the user's "):
        return f"User's {text[11:]}"
    if lowered.startswith("user's "):
        return f"User's {text[7:]}"
    if lowered.startswith("the user "):
        return f"User {text[9:]}"
    if lowered.startswith("user "):
        return f"User {text[5:]}"

    if memory_type == "identity":
        return _normalize_identity_content(text, lowered)
    if memory_type == "preferences":
        return _normalize_preferences_content(text, lowered)
    return _normalize_context_content(text, lowered)


def _normalize_identity_content(text: str, lowered: str) -> str:
    for prefix in ("i am ", "i'm "):
        if lowered.startswith(prefix):
            return f"User is {text[len(prefix) :]}"
    if lowered.startswith("my name is "):
        return f"User's name is {text[11:]}"
    if lowered.startswith(("a ", "an ", "the ")):
        return f"User is {text}"
    if lowered.endswith(IDENTITY_ROLE_SUFFIXES):
        return f"User is a {lowered}"
    return text


def _normalize_preferences_content(text: str, lowered: str) -> str:
    for prefix in ("prefers ", "i prefer "):
        if lowered.startswith(prefix):
            return f"User prefers {text[len(prefix) :]}"
    if lowered.startswith("my preference is "):
        return f"User prefers {text[17:]}"
    return text


def _normalize_context_content(text: str, lowered: str) -> str:
    for prefix, replacement in (
        ("currently ", "User is currently "),
        ("i am currently ", "User is currently "),
        ("i'm currently ", "User is currently "),
        ("working on ", "User is working on "),
        ("i am working on ", "User is working on "),
        ("i'm working on ", "User is working on "),
    ):
        if lowered.startswith(prefix):
            return f"{replacement}{text[len(prefix) :]}"
    return text


def expires_at(memory_type: MemoryType, now: datetime) -> datetime | None:
    if memory_type == "context":
        return now + CONTEXT_TTL
    return None


def targets_non_user_memory(action: dict[str, Any]) -> bool:
    markers = {"agent_memory", "knowledge_base", "kb", "project_memory", "team_memory"}
    for key in ("target", "target_scope", "memory_scope", "destination"):
        value = action.get(key)
        if isinstance(value, str) and value.strip().casefold() in markers:
            return True
    return False


def extraction_user_message(
    conversation: list[dict[str, Any]], snapshot: dict[MemoryType, list[MemoryItem]]
) -> str:
    snapshot_payload = {
        memory_type: [
            {
                "id": item.id,
                "type": item.type,
                "content": item.content,
                "updated_at": store.format_datetime(item.updated_at),
                "expires_at": store.format_datetime(item.expires_at),
            }
            for item in items
        ]
        for memory_type, items in snapshot.items()
    }
    return "\n\n".join(
        [
            "Existing memory snapshot:",
            json.dumps(snapshot_payload, ensure_ascii=False),
            "Conversation:",
            conversation_to_text(conversation),
        ]
    )


def conversation_to_text(conversation: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in conversation:
        role = str(message.get("role", ""))
        if role in {"system", "tool"}:
            continue
        lines.append(f"{role}: {message.get('content', '')}")
    return "\n".join(lines)
