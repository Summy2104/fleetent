"""Management-source persistence for model providers and task_type routing.

This is the single source the admin console writes to (db runtime, named params,
no ORM). model-router runtime consuming these tables instead of its in-code ROUTES
is a model-router-domain follow-up; this module owns only the management writes.

api_key is stored as given (it must be usable for connectivity tests) but is never
returned to clients in plaintext — masking is applied in the API serialization layer.
Pricing columns are nullable: NULL = 未配置 (unset), distinct from an explicit 0.0.
"""

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


_PROVIDER_COLS = (
    "id, base_url, model, api_key, max_tokens, temperature, extra_params, "
    "input_price_per_1k, output_price_per_1k, created_at, updated_at"
)


def add_provider(
    provider_id: str,
    base_url: str,
    model: str,
    api_key: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    extra_params: dict[str, Any] | None = None,
) -> None:
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO model_providers
                (id, base_url, model, api_key, max_tokens, temperature, extra_params,
                 created_at, updated_at)
            VALUES (:id, :base_url, :model, :api_key, :max_tokens, :temperature,
                    :extra_params, :created_at, :updated_at)
            """,
            {
                "id": provider_id,
                "base_url": base_url,
                "model": model,
                "api_key": api_key,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "extra_params": json.dumps(extra_params) if extra_params else None,
                "created_at": now,
                "updated_at": now,
            },
        )


_EDITABLE = {"base_url", "model", "max_tokens", "temperature", "extra_params", "api_key"}


def edit_provider(provider_id: str, **fields: Any) -> None:
    """Update provider fields. ``api_key=None`` means keep the existing key."""
    updates = {k: v for k, v in fields.items() if k in _EDITABLE}
    if "api_key" in updates and updates["api_key"] is None:
        del updates["api_key"]  # blank = unchanged
    if "extra_params" in updates and updates["extra_params"] is not None:
        updates["extra_params"] = json.dumps(updates["extra_params"])
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{k} = :{k}" for k in updates)
    params = {**updates, "id": provider_id}
    with _database().transaction() as conn:
        conn.execute(f"UPDATE model_providers SET {assignments} WHERE id = :id", params)


def set_pricing(provider_id: str, input_price: float | None, output_price: float | None) -> None:
    """Set per-1k-token pricing. Pass None to leave a price 未配置."""
    with _database().transaction() as conn:
        conn.execute(
            """
            UPDATE model_providers
            SET input_price_per_1k = :input_price,
                output_price_per_1k = :output_price,
                updated_at = :updated_at
            WHERE id = :id
            """,
            {
                "id": provider_id,
                "input_price": input_price,
                "output_price": output_price,
                "updated_at": _now(),
            },
        )


def delete_provider(provider_id: str) -> None:
    """Delete a provider and remove it from every task_type route."""
    with _database().transaction() as conn:
        conn.execute("DELETE FROM model_providers WHERE id = :id", {"id": provider_id})
        conn.execute("DELETE FROM model_routes WHERE provider_id = :id", {"id": provider_id})


def get_provider(provider_id: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            f"SELECT {_PROVIDER_COLS} FROM model_providers WHERE id = :id",
            {"id": provider_id},
        )
        .fetchone()
    )
    return _decode(row) if row else None


def list_providers() -> list[dict[str, Any]]:
    rows = (
        _database().execute(f"SELECT {_PROVIDER_COLS} FROM model_providers ORDER BY id").fetchall()
    )
    return [_decode(r) for r in rows]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    if out.get("extra_params"):
        out["extra_params"] = json.loads(out["extra_params"])
    return out


# --- task_type → provider routing (order = fallback priority) -----------------


def set_route_order(task_type: str, provider_ids: list[str]) -> None:
    """Replace the provider list for a task_type; list order is fallback priority."""
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM model_routes WHERE task_type = :task_type",
            {"task_type": task_type},
        )
        for priority, provider_id in enumerate(provider_ids):
            conn.execute(
                """
                INSERT INTO model_routes (task_type, provider_id, priority)
                VALUES (:task_type, :provider_id, :priority)
                """,
                {"task_type": task_type, "provider_id": provider_id, "priority": priority},
            )


def get_route_providers(task_type: str) -> list[str]:
    rows = (
        _database()
        .execute(
            "SELECT provider_id FROM model_routes WHERE task_type = :task_type ORDER BY priority",
            {"task_type": task_type},
        )
        .fetchall()
    )
    return [r["provider_id"] for r in rows]


def list_route_task_types() -> list[str]:
    rows = (
        _database()
        .execute("SELECT DISTINCT task_type FROM model_routes ORDER BY task_type")
        .fetchall()
    )
    return [r["task_type"] for r in rows]
