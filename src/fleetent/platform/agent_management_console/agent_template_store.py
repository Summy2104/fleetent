"""Store-backed, editable agent templates.

Schema lifecycle is owned by Alembic (migration 034, which also seeds the
built-ins). This store reads and writes through the shared DB runtime boundary
using named parameters; it never creates schema. A template is a creation preset
(display_name + allowed_tools + system_prompt) identified by a text ``id``.
"""

import json
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_UNSET: Any = object()


def _db() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_template(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "display_name": str(row["display_name"]),
        "allowed_tools": json.loads(row["allowed_tools"]) if row["allowed_tools"] else [],
        "system_prompt": str(row["system_prompt"]),
    }


def list_templates() -> list[dict[str, Any]]:
    rows = _db().execute("SELECT * FROM agent_templates ORDER BY id").fetchall()
    return [_row_to_template(r) for r in rows]


def get_template(template_id: str) -> dict[str, Any] | None:
    row = (
        _db()
        .execute("SELECT * FROM agent_templates WHERE id = :id", {"id": template_id})
        .fetchone()
    )
    return _row_to_template(row) if row is not None else None


def create_template(
    template_id: str,
    display_name: str,
    allowed_tools: list[str],
    system_prompt: str,
) -> dict[str, Any]:
    """Insert a new template. Raises if the id already exists."""
    now = _now()
    with _db().transaction() as conn:
        if conn.execute(
            "SELECT 1 FROM agent_templates WHERE id = :id", {"id": template_id}
        ).fetchone():
            raise ValueError(f"template {template_id!r} already exists")
        conn.execute(
            "INSERT INTO agent_templates "
            "(id, display_name, allowed_tools, system_prompt, created_at, updated_at) "
            "VALUES (:id, :display_name, :allowed_tools, :system_prompt, :now, :now)",
            {
                "id": template_id,
                "display_name": display_name,
                "allowed_tools": json.dumps(allowed_tools),
                "system_prompt": system_prompt,
                "now": now,
            },
        )
    template = get_template(template_id)
    assert template is not None  # just inserted
    return template


def update_template(
    template_id: str,
    *,
    display_name: Any = _UNSET,
    allowed_tools: Any = _UNSET,
    system_prompt: Any = _UNSET,
) -> dict[str, Any] | None:
    """Edit a template, overriding only provided fields. Returns the row, or None if missing."""
    with _db().transaction() as conn:
        row = conn.execute(
            "SELECT * FROM agent_templates WHERE id = :id", {"id": template_id}
        ).fetchone()
        if row is None:
            return None
        new_display = row["display_name"] if display_name is _UNSET else display_name
        new_tools = row["allowed_tools"] if allowed_tools is _UNSET else json.dumps(allowed_tools)
        new_prompt = row["system_prompt"] if system_prompt is _UNSET else system_prompt
        conn.execute(
            "UPDATE agent_templates SET display_name = :display_name, "
            "allowed_tools = :allowed_tools, system_prompt = :system_prompt, updated_at = :now "
            "WHERE id = :id",
            {
                "id": template_id,
                "display_name": new_display,
                "allowed_tools": new_tools,
                "system_prompt": new_prompt,
                "now": _now(),
            },
        )
    return get_template(template_id)


def delete_template(template_id: str) -> bool:
    """Remove a template. Returns True if a row was deleted, False if none existed."""
    with _db().transaction() as conn:
        if (
            conn.execute(
                "SELECT 1 FROM agent_templates WHERE id = :id", {"id": template_id}
            ).fetchone()
            is None
        ):
            return False
        conn.execute("DELETE FROM agent_templates WHERE id = :id", {"id": template_id})
    return True
