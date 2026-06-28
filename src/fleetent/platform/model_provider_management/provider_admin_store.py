"""Management-source persistence for provider credentials on split registry tables."""

import datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


_PROVIDER_COLS = "id, description, vendor, api_key, api_key_env, base_url, created_at, updated_at"


def add_provider(
    provider_id: str,
    base_url: str | None = None,
    model: str | None = None,
    description: str | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
    extra_params: dict[str, Any] | None = None,
    provider: str | None = None,
    protocol: str | None = None,
    api_key_env: str | None = None,
    params: dict[str, Any] | None = None,
) -> None:
    """Insert a provider row.

    The ``model``-related arguments are kept only as a transition shim for existing
    tests/helpers; when present, a same-id model row is created in ``models``.
    """
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO providers
                (id, description, vendor, api_key, api_key_env, base_url, created_at, updated_at)
            VALUES
                (
                    :id, :description, :vendor, :api_key, :api_key_env, :base_url,
                    :created_at, :updated_at
                )
            """,
            {
                "id": provider_id,
                "description": description,
                "vendor": provider,
                "api_key": api_key,
                "api_key_env": api_key_env,
                "base_url": base_url,
                "created_at": now,
                "updated_at": now,
            },
        )

    if (
        model is not None
        or protocol is not None
        or max_tokens is not None
        or params
        or extra_params
    ):
        from fleetent.platform.model_provider_management import model_admin_store

        endpoint = None
        normalized_base_url = base_url
        if protocol in {"http_embedding", "http_rerank", "openai_image_generation"}:
            endpoint = base_url
            normalized_base_url = base_url
        model_admin_store.add_model(
            provider_id,
            provider_id=provider_id,
            protocol=protocol,
            model_name=model,
            base_url=normalized_base_url,
            endpoint=endpoint,
            max_tokens=max_tokens,
            params=params,
            extra_params=extra_params,
            description=description,
        )


_EDITABLE = {"description", "vendor", "base_url", "api_key", "api_key_env"}


def edit_provider(provider_id: str, **fields: Any) -> None:
    """Update provider fields. ``api_key=None`` means keep the existing key."""
    updates = {key: value for key, value in fields.items() if key in _EDITABLE}
    if "api_key" in updates and updates["api_key"] is None:
        del updates["api_key"]
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = :{key}" for key in updates)
    with _database().transaction() as conn:
        conn.execute(
            f"UPDATE providers SET {assignments} WHERE id = :id",
            {**updates, "id": provider_id},
        )


def set_pricing(provider_id: str, input_price: float | None, output_price: float | None) -> None:
    """Compatibility shim for legacy callers that still think pricing is provider-level."""
    from fleetent.platform.model_provider_management import model_admin_store

    model_admin_store.edit_model(
        provider_id,
        input_price_per_1k=input_price,
        output_price_per_1k=output_price,
    )


def delete_provider(provider_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute("DELETE FROM providers WHERE id = :id", {"id": provider_id})


def get_provider(provider_id: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            f"SELECT {_PROVIDER_COLS} FROM providers WHERE id = :id",
            {"id": provider_id},
        )
        .fetchone()
    )
    return dict(row) if row else None


def list_providers() -> list[dict[str, Any]]:
    rows = _database().execute(f"SELECT {_PROVIDER_COLS} FROM providers ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def provider_key_for_env(env_name: str) -> str | None:
    row = (
        _database()
        .execute(
            """
        SELECT api_key
        FROM providers
        WHERE api_key_env = :env_name AND api_key IS NOT NULL
        ORDER BY id
        LIMIT 1
        """,
            {"env_name": env_name},
        )
        .fetchone()
    )
    if row is None:
        return None
    return str(row["api_key"])
