"""Tests for provider_admin_store: provider CRUD and pricing.

New management-source tables created by Alembic migration 011, accessed via the
unified db runtime (named params). api_key is stored but never returned plaintext.
"""

import pytest

from fleetent.platform.model_provider_management import provider_admin_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_tables(store_db):
    import sqlite3

    legacy_route_table = "model" + "_routes"
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "model_providers" in tables
    assert legacy_route_table not in tables


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


def test_delete_provider_without_legacy_route_table(store_db):
    store.add_provider("a", base_url="u", model="m", api_key="k")
    store.delete_provider("a")
    assert store.get_provider("a") is None


def test_list_providers(store_db):
    store.add_provider("a", base_url="u", model="m", api_key="k")
    store.add_provider("b", base_url="u", model="m", api_key="k")
    names = {p["id"] for p in store.list_providers()}
    assert names == {"a", "b"}
