"""Integration tests: management tables onboarded into alembic.

Covers:
- upgrade head creates api_keys / audit_log and removes owner-level IM connectors
- current head columns match the live schema
- upgrade preserves compatible existing data and drops descope'd allowlist tables
- fresh upgrade → downgrade → upgrade roundtrip
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")
_LEGACY_TABLE = "_".join(("im", "channel", "allowlist"))
_LEGACY_FLAG = "_".join(("allowlist", "enforced"))
_OWNER_TABLE = "_".join(("im", "connectors"))


def _apply(db_path: Path, revision: str = "head") -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _downgrade(db_path: Path, revision: str = "base") -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, revision)


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _cols(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _row(db_path: Path, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchone()


# ---------------------------------------------------------------------------
# 2.1 schema after upgrade head
# ---------------------------------------------------------------------------


def test_upgrade_creates_api_keys(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert "api_keys" in _tables(db)
    assert _cols(db, "api_keys") == {
        "id",
        "user_id",
        "key_hash",
        "prefix",
        "scope",
        "note",
        "expires_at",
        "revoked_at",
        "created_at",
        "last_used_at",
        "last_ip",
        "last_ua",
        "call_count",
    }


def test_upgrade_creates_audit_log(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert "audit_log" in _tables(db)
    assert _cols(db, "audit_log") == {
        "id",
        "actor_user_id",
        "action",
        "target_type",
        "target_id",
        "detail",
        "batch_id",
        "created_at",
    }


def test_upgrade_drops_owner_level_im_table(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    assert _OWNER_TABLE not in _tables(db)


def test_upgrade_head_drops_platform_kb_ingest_tables(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    tables = _tables(db)
    assert "kb_connectors" not in tables
    assert "kb_ingest_jobs" not in tables
    assert "kb_connector_schedule_state" not in tables


# ---------------------------------------------------------------------------
# 2.3 idempotency: existing tables survive upgrade (no data loss)
# ---------------------------------------------------------------------------


def test_upgrade_deletes_orphan_api_keys(tmp_path):
    db = tmp_path / "t.db"
    # Pre-create via _init_db DDL, insert a row
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS api_keys (
                id           INTEGER PRIMARY KEY,
                user_id      TEXT NOT NULL,
                key_hash     TEXT UNIQUE NOT NULL,
                prefix       TEXT NOT NULL,
                scope        TEXT NOT NULL DEFAULT '["*"]',
                note         TEXT,
                expires_at   TEXT,
                revoked_at   TEXT,
                created_at   TEXT NOT NULL,
                last_used_at TEXT,
                last_ip      TEXT,
                last_ua      TEXT,
                call_count   INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            "INSERT INTO api_keys (user_id, key_hash, prefix, scope, created_at, call_count)"
            " VALUES ('u1', 'hash1', 'ma-prefix', '[\"*\"]', '2026-01-01T00:00:00+00:00', 0)"
        )
    _apply(db)
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
    assert count == 0, "orphan api_keys row must be deleted during upgrade"


def test_upgrade_noop_on_existing_audit_log(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id            INTEGER PRIMARY KEY,
                actor_user_id TEXT,
                action        TEXT NOT NULL,
                target_type   TEXT,
                target_id     TEXT,
                detail        TEXT,
                batch_id      TEXT,
                created_at    TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT INTO audit_log (action, created_at)"
            " VALUES ('create_user', '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert count == 1


def test_upgrade_drops_existing_owner_level_im_table(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {_OWNER_TABLE} (
                id                 INTEGER PRIMARY KEY,
                owner_id           TEXT NOT NULL,
                platform           TEXT NOT NULL,
                enabled            INTEGER NOT NULL DEFAULT 0,
                """
            + _LEGACY_FLAG
            + """ INTEGER NOT NULL DEFAULT 0,
                config             TEXT,
                status             TEXT NOT NULL DEFAULT 'stopped',
                last_heartbeat_at  TEXT,
                last_error         TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL,
                UNIQUE(owner_id, platform)
            )"""
        )
        conn.execute(
            f"INSERT INTO {_OWNER_TABLE}"
            f" (owner_id, platform, enabled, {_LEGACY_FLAG}, status, created_at, updated_at)"
            " VALUES ('owner1', 'slack', 1, 0, 'connected',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    assert _OWNER_TABLE not in _tables(db)


def test_upgrade_drops_existing_legacy_allowlist_table(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {_LEGACY_TABLE} (
                id         INTEGER PRIMARY KEY,
                owner_id   TEXT NOT NULL,
                platform   TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_id   TEXT NOT NULL,
                allowed    INTEGER NOT NULL DEFAULT 1,
                note       TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(owner_id, platform, scope_type, scope_id)
            )"""
        )
        conn.execute(
            f"INSERT INTO {_LEGACY_TABLE}"
            " (owner_id, platform, scope_type, scope_id, allowed, created_at)"
            " VALUES ('owner1', 'slack', 'channel', 'C123', 1, '2026-01-01T00:00:00+00:00')"
        )
    _apply(db)
    assert _LEGACY_TABLE not in _tables(db)


# ---------------------------------------------------------------------------
# 2.3 roundtrip: upgrade → downgrade → upgrade on fresh db
# ---------------------------------------------------------------------------


def test_roundtrip_upgrade_downgrade_upgrade(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)
    tables_after_upgrade = _tables(db)
    assert "api_keys" in tables_after_upgrade
    assert "audit_log" in tables_after_upgrade
    assert _OWNER_TABLE not in tables_after_upgrade
    assert _LEGACY_TABLE not in tables_after_upgrade

    _downgrade(db)
    tables_after_downgrade = _tables(db)
    assert "api_keys" not in tables_after_downgrade
    assert "audit_log" not in tables_after_downgrade
    assert _OWNER_TABLE not in tables_after_downgrade
    assert _LEGACY_TABLE not in tables_after_downgrade

    _apply(db)
    tables_after_reupgrade = _tables(db)
    assert "api_keys" in tables_after_reupgrade
    assert "audit_log" in tables_after_reupgrade
    assert _OWNER_TABLE not in tables_after_reupgrade
    assert _LEGACY_TABLE not in tables_after_reupgrade


def test_upgrade_creates_provider_and_model_tables(tmp_path):
    db = tmp_path / "t.db"
    _apply(db)

    assert "providers" in _tables(db)
    assert "models" in _tables(db)
    assert _cols(db, "providers") == {
        "id",
        "vendor",
        "api_key",
        "api_key_env",
        "base_url",
        "description",
        "created_at",
        "updated_at",
    }
    assert _cols(db, "models") == {
        "id",
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
        "created_at",
        "updated_at",
    }
    assert "api_key" not in _cols(db, "models")
    assert "api_key_env" not in _cols(db, "models")
    assert "temperature" not in _cols(db, "providers")
    assert "temperature" not in _cols(db, "models")


def test_upgrade_backfills_model_providers_into_provider_and_model_rows(tmp_path):
    db = tmp_path / "t.db"
    _apply(db, "106")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO model_providers (
                id, description, provider, protocol, base_url, model, api_key, api_key_env,
                max_tokens, temperature, extra_params, params,
                input_price_per_1k, output_price_per_1k, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-openai",
                "legacy row",
                "openai",
                "openai_chat",
                "https://api.openai.example/v1",
                "gpt-5",
                "sk-legacy",
                "OPENAI_API_KEY",
                4096,
                0.7,
                '{"top_p": 0.9}',
                '{"reasoning_effort":"medium"}',
                1.25,
                5.0,
                "2026-06-01T00:00:00+00:00",
                "2026-06-02T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO model_providers (
                id, description, provider, protocol, base_url, model, api_key, api_key_env,
                max_tokens, temperature, extra_params, params,
                input_price_per_1k, output_price_per_1k, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-custom",
                "fallback vendor id",
                None,
                "http_embedding",
                "https://embed.example/api",
                "embed-1",
                None,
                "EMBED_API_KEY",
                1024,
                None,
                None,
                '{"truncate":"end"}',
                None,
                0.2,
                "2026-06-03T00:00:00+00:00",
                "2026-06-04T00:00:00+00:00",
            ),
        )
        conn.commit()

    _apply(db)

    provider = _row(db, "SELECT * FROM providers WHERE id = ?", ("openai",))
    assert provider is not None
    assert provider["vendor"] == "openai"
    assert provider["api_key"] == "sk-legacy"
    assert provider["api_key_env"] == "OPENAI_API_KEY"
    assert provider["base_url"] == "https://api.openai.example/v1"
    assert provider["description"] == "legacy row"

    model = _row(db, "SELECT * FROM models WHERE id = ?", ("legacy-openai",))
    assert model is not None
    assert model["id"] == "legacy-openai"
    assert model["provider_id"] == "openai"
    assert model["protocol"] == "openai_chat"
    assert model["model_name"] == "gpt-5"
    assert model["base_url"] == "https://api.openai.example/v1"
    assert model["max_tokens"] == 4096
    assert model["params"] == '{"reasoning_effort":"medium"}'
    assert model["extra_params"] == '{"top_p": 0.9}'
    assert model["input_price_per_1k"] == 1.25
    assert model["output_price_per_1k"] == 5.0

    fallback_provider = _row(
        db, "SELECT * FROM providers WHERE id = ?", ("legacy-custom__provider",)
    )
    assert fallback_provider is not None
    assert fallback_provider["vendor"] is None
    fallback_model = _row(db, "SELECT * FROM models WHERE id = ?", ("legacy-custom",))
    assert fallback_model is not None
    assert fallback_model["provider_id"] == "legacy-custom__provider"
    assert fallback_model["model_name"] == "embed-1"
    assert "model_providers" not in _tables(db)


def test_downgrade_rebuilds_model_providers_from_split_tables(tmp_path):
    db = tmp_path / "t.db"
    _apply(db, "106")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO model_providers (
                id, description, provider, protocol, base_url, model, api_key, api_key_env,
                max_tokens, temperature, extra_params, params,
                input_price_per_1k, output_price_per_1k, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-anthropic",
                "anthropic row",
                "anthropic",
                "openai_chat",
                "https://anthropic.example/v1",
                "claude-sonnet",
                "sk-ant",
                "ANTHROPIC_API_KEY",
                8192,
                0.2,
                '{"top_p": 0.95}',
                '{"temperature":0.2}',
                3.0,
                15.0,
                "2026-06-10T00:00:00+00:00",
                "2026-06-11T00:00:00+00:00",
            ),
        )
        conn.commit()
    _apply(db)

    _downgrade(db, "106")

    assert "providers" not in _tables(db)
    assert "models" not in _tables(db)
    row = _row(db, "SELECT * FROM model_providers WHERE id = ?", ("legacy-anthropic",))
    assert row is not None
    assert row["provider"] == "anthropic"
    assert row["model"] == "claude-sonnet"
    assert row["api_key"] == "sk-ant"
    assert row["api_key_env"] == "ANTHROPIC_API_KEY"
    assert row["base_url"] == "https://anthropic.example/v1"
    assert row["temperature"] is None
    assert row["params"] == '{"temperature":0.2}'
    assert row["extra_params"] == '{"top_p": 0.95}'
