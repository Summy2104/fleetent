"""split model registry into providers and models

Revision ID: 107
Revises: 106
Create Date: 2026-06-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "107"
down_revision = "106"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _provider_id_for_row(
    row: sa.RowMapping,
    used_ids: set[str],
) -> str:
    vendor = row["provider"]
    legacy_id = row["id"]
    if vendor and vendor not in used_ids:
        used_ids.add(vendor)
        return vendor
    candidate = f"{legacy_id}__provider"
    used_ids.add(candidate)
    return candidate


def _create_new_tables() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("vendor", sa.Text(), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("api_key_env", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "models",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("protocol", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("input_price_per_1k", sa.Float(), nullable=True),
        sa.Column("output_price_per_1k", sa.Float(), nullable=True),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("extra_params", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_models_provider_id", "models", ["provider_id"])
    op.create_index("idx_models_protocol", "models", ["protocol"])


def _backfill_to_new_tables() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, description, provider, protocol, base_url, model, api_key, api_key_env,
                   max_tokens, extra_params, params, input_price_per_1k, output_price_per_1k,
                   created_at, updated_at
            FROM model_providers
            ORDER BY id
            """
        )
    ).mappings()
    used_provider_ids: set[str] = set()
    for row in rows:
        provider_id = _provider_id_for_row(row, used_provider_ids)
        bind.execute(
            sa.text(
                """
                INSERT INTO providers (
                    id, vendor, api_key, api_key_env, base_url, description, created_at, updated_at
                ) VALUES (
                    :id, :vendor, :api_key, :api_key_env, :base_url, :description,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "id": provider_id,
                "vendor": row["provider"],
                "api_key": row["api_key"],
                "api_key_env": row["api_key_env"],
                "base_url": row["base_url"],
                "description": row["description"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )
        endpoint = row["base_url"] if row["protocol"] in {
            "http_embedding",
            "http_rerank",
            "openai_image_generation",
        } else None
        bind.execute(
            sa.text(
                """
                INSERT INTO models (
                    id, provider_id, protocol, model_name, base_url, endpoint, max_tokens,
                    input_price_per_1k, output_price_per_1k, params, extra_params,
                    description, created_at, updated_at
                ) VALUES (
                    :id, :provider_id, :protocol, :model_name, :base_url, :endpoint, :max_tokens,
                    :input_price_per_1k, :output_price_per_1k, :params, :extra_params,
                    :description, :created_at, :updated_at
                )
                """
            ),
            {
                "id": row["id"],
                "provider_id": provider_id,
                "protocol": row["protocol"],
                "model_name": row["model"],
                "base_url": row["base_url"],
                "endpoint": endpoint,
                "max_tokens": row["max_tokens"],
                "input_price_per_1k": row["input_price_per_1k"],
                "output_price_per_1k": row["output_price_per_1k"],
                "params": row["params"],
                "extra_params": row["extra_params"],
                "description": row["description"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )


def _create_legacy_table() -> None:
    op.create_table(
        "model_providers",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("extra_params", sa.Text(), nullable=True),
        sa.Column("input_price_per_1k", sa.Float(), nullable=True),
        sa.Column("output_price_per_1k", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("protocol", sa.Text(), nullable=True),
        sa.Column("api_key_env", sa.Text(), nullable=True),
        sa.Column("params", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def _backfill_to_legacy_table() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                models.id,
                models.base_url,
                models.endpoint,
                models.model_name,
                providers.api_key,
                models.max_tokens,
                models.extra_params,
                models.input_price_per_1k,
                models.output_price_per_1k,
                models.created_at,
                models.updated_at,
                models.description,
                providers.vendor,
                models.protocol,
                providers.api_key_env,
                models.params
            FROM models
            JOIN providers ON providers.id = models.provider_id
            ORDER BY models.id
            """
        )
    ).mappings()
    for row in rows:
        base_url = row["base_url"] or row["endpoint"]
        bind.execute(
            sa.text(
                """
                INSERT INTO model_providers (
                    id, base_url, model, api_key, max_tokens, temperature, extra_params,
                    input_price_per_1k, output_price_per_1k, created_at, updated_at,
                    description, provider, protocol, api_key_env, params
                ) VALUES (
                    :id, :base_url, :model, :api_key, :max_tokens, NULL, :extra_params,
                    :input_price_per_1k, :output_price_per_1k, :created_at, :updated_at,
                    :description, :provider, :protocol, :api_key_env, :params
                )
                """
            ),
            {
                "id": row["id"],
                "base_url": base_url,
                "model": row["model_name"],
                "api_key": row["api_key"],
                "max_tokens": row["max_tokens"],
                "extra_params": row["extra_params"],
                "input_price_per_1k": row["input_price_per_1k"],
                "output_price_per_1k": row["output_price_per_1k"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "description": row["description"],
                "provider": row["vendor"],
                "protocol": row["protocol"],
                "api_key_env": row["api_key_env"],
                "params": row["params"],
            },
        )


def upgrade() -> None:
    if _has_table("providers") and _has_table("models"):
        return
    _create_new_tables()
    if _has_table("model_providers"):
        _backfill_to_new_tables()
        op.drop_table("model_providers")


def downgrade() -> None:
    if _has_table("model_providers"):
        return
    _create_legacy_table()
    if _has_table("models") and _has_table("providers"):
        _backfill_to_legacy_table()
        op.drop_index("idx_models_protocol", table_name="models")
        op.drop_index("idx_models_provider_id", table_name="models")
        op.drop_table("models")
        op.drop_table("providers")
