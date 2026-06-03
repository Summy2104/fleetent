"""Tests for provider_admin_store: provider CRUD, task_type route ordering, pricing.

New management-source tables created by Alembic migration 011, accessed via the
unified db runtime (named params). api_key is stored but never returned plaintext.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.model_provider_management import provider_admin_store as store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_tables(store_db):
    import sqlite3

    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "model_providers" in tables
    assert "model_routes" in tables


def test_add_and_get_provider(store_db):
    store.add_provider(
        "openai-gpt",
        base_url="https://api.openai.com/v1/",
        model="gpt-5.5",
        api_key="sk-secret",
        max_tokens=4096,
        temperature=0.7,
        extra_params={"top_p": 0.9},
    )
    p = store.get_provider("openai-gpt")
    assert p["base_url"] == "https://api.openai.com/v1/"
    assert p["model"] == "gpt-5.5"
    assert p["api_key"] == "sk-secret"  # raw stored; masking happens in the API layer
    assert p["max_tokens"] == 4096


def test_pricing_defaults_to_unset_not_zero(store_db):
    store.add_provider("p", base_url="u", model="m", api_key="k")
    p = store.get_provider("p")
    assert p["input_price_per_1k"] is None  # 未配置, not 0
    assert p["output_price_per_1k"] is None


def test_set_pricing_distinguishes_explicit_zero(store_db):
    store.add_provider("p", base_url="u", model="m", api_key="k")
    store.set_pricing("p", input_price=0.0, output_price=0.0)
    p = store.get_provider("p")
    assert p["input_price_per_1k"] == 0.0  # explicit 0 is configured
    assert p["output_price_per_1k"] == 0.0


def test_edit_provider_blank_key_keeps_existing(store_db):
    store.add_provider("p", base_url="u", model="m", api_key="orig-key")
    store.edit_provider("p", base_url="u2", api_key=None)  # None = unchanged
    p = store.get_provider("p")
    assert p["base_url"] == "u2"
    assert p["api_key"] == "orig-key"


def test_delete_provider_removes_from_routes(store_db):
    store.add_provider("a", base_url="u", model="m", api_key="k")
    store.add_provider("b", base_url="u", model="m", api_key="k")
    store.set_route_order("default", ["a", "b"])
    store.delete_provider("a")
    assert store.get_provider("a") is None
    assert store.get_route_providers("default") == ["b"]


def test_list_providers(store_db):
    store.add_provider("a", base_url="u", model="m", api_key="k")
    store.add_provider("b", base_url="u", model="m", api_key="k")
    names = {p["id"] for p in store.list_providers()}
    assert names == {"a", "b"}


def test_route_order_is_fallback_priority(store_db):
    store.add_provider("a", base_url="u", model="m", api_key="k")
    store.add_provider("b", base_url="u", model="m", api_key="k")
    store.set_route_order("code", ["a", "b"])
    assert store.get_route_providers("code") == ["a", "b"]
    store.set_route_order("code", ["b", "a"])  # reorder
    assert store.get_route_providers("code") == ["b", "a"]


def test_route_unconfigured_returns_empty(store_db):
    assert store.get_route_providers("never") == []
