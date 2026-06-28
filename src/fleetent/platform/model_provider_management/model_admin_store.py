"""Management-source persistence for models on split registry tables."""

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


_MODEL_COLS = (
    "id, provider_id, protocol, model_name, base_url, endpoint, max_tokens, "
    "input_price_per_1k, output_price_per_1k, params, extra_params, "
    "description, created_at, updated_at"
)
_JSON_FIELDS = {"params", "extra_params"}
_EDITABLE = {
    "provider_id",
    "protocol",
    "model_name",
    "base_url",
    "endpoint",
    "max_tokens",
    "input_price_per_1k",
    "output_price_per_1k",
    "params",
    "extra_params",
    "description",
}


def add_model(
    model_id: str,
    *,
    provider_id: str,
    protocol: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    endpoint: str | None = None,
    max_tokens: int | None = None,
    input_price_per_1k: float | None = None,
    output_price_per_1k: float | None = None,
    params: dict[str, Any] | None = None,
    extra_params: dict[str, Any] | None = None,
    description: str | None = None,
) -> None:
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            f"""
            INSERT INTO models ({_MODEL_COLS})
            VALUES (
                :id, :provider_id, :protocol, :model_name, :base_url, :endpoint, :max_tokens,
                :input_price_per_1k, :output_price_per_1k, :params, :extra_params,
                :description, :created_at, :updated_at
            )
            """,
            {
                "id": model_id,
                "provider_id": provider_id,
                "protocol": protocol,
                "model_name": model_name,
                "base_url": base_url,
                "endpoint": endpoint,
                "max_tokens": max_tokens,
                "input_price_per_1k": input_price_per_1k,
                "output_price_per_1k": output_price_per_1k,
                "params": json.dumps(params) if params is not None else None,
                "extra_params": json.dumps(extra_params) if extra_params is not None else None,
                "description": description,
                "created_at": now,
                "updated_at": now,
            },
        )


def edit_model(model_id: str, **fields: Any) -> None:
    updates = {key: value for key, value in fields.items() if key in _EDITABLE}
    for field in _JSON_FIELDS:
        if field in updates and updates[field] is not None:
            updates[field] = json.dumps(updates[field])
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = :{key}" for key in updates)
    with _database().transaction() as conn:
        conn.execute(
            f"UPDATE models SET {assignments} WHERE id = :id",
            {**updates, "id": model_id},
        )


def delete_model(model_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute("DELETE FROM models WHERE id = :id", {"id": model_id})


def get_model(model_id: str) -> dict[str, Any] | None:
    row = _database().execute(
        f"SELECT {_MODEL_COLS} FROM models WHERE id = :id",
        {"id": model_id},
    ).fetchone()
    return _decode(row) if row else None


def list_models(
    *,
    provider_id: str | None = None,
    protocol: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if provider_id is not None:
        clauses.append("provider_id = :provider_id")
        params["provider_id"] = provider_id
    if protocol is not None:
        clauses.append("protocol = :protocol")
        params["protocol"] = protocol
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _database().execute(
        f"SELECT {_MODEL_COLS} FROM models{where} ORDER BY id",
        params,
    ).fetchall()
    return [_decode(row) for row in rows]


def references_for_model(model_id: str) -> dict[str, list[str]]:
    agents: list[str] = []
    for row in _database().execute(
        "SELECT name, model_overrides FROM agents ORDER BY name",
    ).fetchall():
        overrides = json.loads(row["model_overrides"] or "{}")
        if model_id in _referenced_model_ids(overrides):
            agents.append(str(row["name"]))
    return {"agents": agents, "models": [model_id] if agents else []}


def references_for_provider(provider_id: str) -> dict[str, list[str]]:
    models = [str(row["id"]) for row in list_models(provider_id=provider_id)]
    if not models:
        return {"agents": [], "models": []}
    referenced_agents: set[str] = set()
    referenced_models: set[str] = set()
    model_id_set = set(models)
    for row in _database().execute(
        "SELECT name, model_overrides FROM agents ORDER BY name",
    ).fetchall():
        overrides = json.loads(row["model_overrides"] or "{}")
        matches = _referenced_model_ids(overrides) & model_id_set
        if matches:
            referenced_agents.add(str(row["name"]))
            referenced_models.update(matches)
    return {
        "agents": sorted(referenced_agents),
        "models": [model_id for model_id in models if model_id in referenced_models],
    }


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for field in _JSON_FIELDS:
        if out.get(field):
            out[field] = json.loads(out[field])
    return out


def _referenced_model_ids(model_overrides: dict[str, Any]) -> set[str]:
    route_overrides = {
        key: value for key, value in model_overrides.items() if key != "__secrets__"
    }
    routes_block = route_overrides.get("routes")
    if isinstance(routes_block, dict):
        route_overrides = routes_block
    referenced: set[str] = set()
    for raw_entries in route_overrides.values():
        entries = raw_entries if isinstance(raw_entries, list) else [raw_entries]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for key in ("model_id", "provider_id", "target", "provider"):
                value = entry.get(key)
                if isinstance(value, str) and value:
                    referenced.add(value)
                    break
    return referenced
