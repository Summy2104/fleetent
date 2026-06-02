"""LLM extraction workflow for User Memory."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fleetent.intelligence import vector_store
from fleetent.intelligence.memory import store
from fleetent.intelligence.memory.models import MemoryItem, MemoryType
from fleetent.model_router import get_async_client_and_config

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


async def extract_and_update(
    user_id: str, conversation: list[dict[str, Any]], namespace: str = "default"
) -> None:
    """Extract structured memories from conversation and update the memory store."""
    snapshot = store.memory_snapshot(user_id, namespace)
    vector_ns = vector_store.memory_namespace(user_id, namespace)
    client, cfg = get_async_client_and_config("memory_extraction")
    response = await client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": extraction_user_message(conversation, snapshot)},
        ],
        max_tokens=cfg.max_tokens,
    )
    raw = strip_markdown_fence(response.choices[0].message.content or "[]")
    try:
        actions = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(actions, list):
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
            await vector_store.delete(target.id, vector_ns)
            continue
        content = action.get("content")
        raw_type = action.get("type")
        if not isinstance(content, str) or not content.strip() or raw_type not in VALID_TYPES:
            continue
        memory_type = cast(MemoryType, raw_type)
        if action_name == "update":
            target_id = action.get("target_id")
            target = snapshot_by_id.get(target_id) if isinstance(target_id, str) else None
            if target is None or target.type != memory_type:
                continue
            updated = MemoryItem(
                id=target.id,
                user_id=user_id,
                type=target.type,
                content=content.strip(),
                created_at=target.created_at,
                updated_at=now,
                expires_at=expires_at(memory_type, now),
                namespace=namespace,
            )
            store.update_memory(updated)
            await vector_store.upsert(updated.id, updated.content, vector_ns)
            continue
        if action_name != "create":
            continue
        item = MemoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=memory_type,
            content=content.strip(),
            created_at=now,
            updated_at=now,
            expires_at=expires_at(memory_type, now),
            namespace=namespace,
        )
        store.insert_memory(item)
        await vector_store.upsert(item.id, item.content, vector_ns)


def strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def expires_at(memory_type: MemoryType, now: datetime) -> datetime | None:
    if memory_type == "context":
        return now + CONTEXT_TTL
    return None


def targets_non_user_memory(action: dict[str, Any]) -> bool:
    markers = {"shared_memory", "knowledge_base", "kb", "project_memory", "team_memory"}
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
