"""Credential slot metadata stored with the current agent config."""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from typing import Literal

from fleetent import agent_store
from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

RESERVED_KEY = "__credential_slots__"
SlotMode = Literal["operator", "inject"]


@dataclass(frozen=True)
class CredentialSlot:
    slot_key: str
    env_name: str
    mode: SlotMode


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def ensure_slot(
    agent: agent_store.Agent,
    slot_key: str,
    *,
    mode: SlotMode | None = None,
    env_name: str | None = None,
) -> CredentialSlot:
    """Create or update metadata for one credential slot on the current agent config."""
    if not slot_key.strip():
        raise ValueError("slot_key is required")
    if mode is not None and mode not in {"operator", "inject"}:
        raise ValueError(f"unknown credential slot mode: {mode}")

    db = _database()
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT model_overrides FROM agents WHERE id = :agent_id",
            {"agent_id": agent.id},
        ).fetchone()
        if row is None:
            raise ValueError(f"agent {agent.name!r} not found")

        overrides = json.loads(row["model_overrides"] or "{}")
        slots = _slots_from_overrides(overrides)
        existing = slots.get(slot_key, {})
        next_env_name = (
            env_name or existing.get("env_name") or derive_env_name(agent.name, slot_key)
        )
        next_mode: SlotMode = mode or existing.get("mode") or "operator"  # type: ignore[assignment]
        _reject_duplicate_env(slots, slot_key, next_env_name)
        slots[slot_key] = {"env_name": next_env_name, "mode": next_mode}
        overrides[RESERVED_KEY] = slots
        conn.execute(
            "UPDATE agents SET model_overrides = :model_overrides WHERE id = :agent_id",
            {
                "model_overrides": json.dumps(overrides),
                "agent_id": agent.id,
            },
        )
    return CredentialSlot(slot_key=slot_key, env_name=next_env_name, mode=next_mode)


def list_slots(agent: agent_store.Agent) -> list[CredentialSlot]:
    """List credential slots for the current agent config."""
    row = (
        _database()
        .execute(
            "SELECT model_overrides FROM agents WHERE id = :agent_id",
            {"agent_id": agent.id},
        )
        .fetchone()
    )
    if row is None:
        return []
    slots = _slots_from_overrides(json.loads(row["model_overrides"] or "{}"))
    return [
        CredentialSlot(
            slot_key=slot_key,
            env_name=str(data["env_name"]),
            mode=str(data.get("mode") or "operator"),  # type: ignore[arg-type]
        )
        for slot_key, data in sorted(slots.items())
    ]


def derive_env_name(agent_name: str, slot_key: str) -> str:
    """Derive a stable default env name for a newly-created slot."""
    return f"FLEETENT_AGENT_{_upper_snake(agent_name)}_{_upper_snake(slot_key)}"


def _slots_from_overrides(overrides: dict[str, object]) -> dict[str, dict[str, str]]:
    raw = overrides.get(RESERVED_KEY)
    if not isinstance(raw, dict):
        return {}
    slots: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, dict):
            env_name = value.get("env_name")
            if isinstance(env_name, str) and env_name:
                mode = (
                    value.get("mode") if value.get("mode") in {"operator", "inject"} else "operator"
                )
                slots[key] = {"env_name": env_name, "mode": str(mode)}
    return slots


def _reject_duplicate_env(slots: dict[str, dict[str, str]], slot_key: str, env_name: str) -> None:
    for other_key, other in slots.items():
        if other_key != slot_key and other.get("env_name") == env_name:
            raise ValueError(f"duplicate env_name {env_name!r} for credential slots")


def _upper_snake(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return normalized.upper() or "DEFAULT"
