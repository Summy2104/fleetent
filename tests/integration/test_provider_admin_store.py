"""Integration tests for provider_admin_store on split providers/models tables."""

import pytest

from fleetent.platform.model_provider_management import provider_admin_store as provider_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_providers_and_models_tables(store_db):
    import sqlite3

    with sqlite3.connect(store_db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "providers" in tables
    assert "models" in tables
    assert "model_providers" not in tables


def test_add_and_get_provider_without_model_fields(store_db):
    provider_store.add_provider(
        "openai",
        description="shared openai credentials",
        provider="openai",
        base_url="https://api.openai.example/v1",
        api_key="sk-secret",
        api_key_env="OPENAI_API_KEY",
    )

    provider = provider_store.get_provider("openai")

    assert provider == {
        "id": "openai",
        "description": "shared openai credentials",
        "vendor": "openai",
        "api_key": "sk-secret",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.example/v1",
        "created_at": provider["created_at"],
        "updated_at": provider["updated_at"],
    }


def test_provider_key_for_env_reads_providers_table(store_db):
    provider_store.add_provider(
        "p1", provider="anthropic", api_key="sk-1", api_key_env="ANTHROPIC_KEY"
    )
    provider_store.add_provider("p2", provider="openai", api_key=None, api_key_env="OPENAI_KEY")

    assert provider_store.provider_key_for_env("ANTHROPIC_KEY") == "sk-1"
    assert provider_store.provider_key_for_env("OPENAI_KEY") is None
    assert provider_store.provider_key_for_env("MISSING") is None


def test_edit_provider_blank_key_keeps_existing(store_db):
    provider_store.add_provider("p", provider="openai", api_key="orig-key", base_url="https://one")

    provider_store.edit_provider("p", base_url="https://two", api_key=None)

    provider = provider_store.get_provider("p")
    assert provider is not None
    assert provider["base_url"] == "https://two"
    assert provider["api_key"] == "orig-key"


def test_delete_provider_without_models(store_db):
    provider_store.add_provider("solo", provider="openai")

    provider_store.delete_provider("solo")

    assert provider_store.get_provider("solo") is None


def test_list_providers_returns_provider_rows_only(store_db):
    provider_store.add_provider("a", provider="openai")
    provider_store.add_provider("b", provider="anthropic")

    providers = provider_store.list_providers()

    assert {provider["id"] for provider in providers} == {"a", "b"}
    assert all("model" not in provider for provider in providers)
    assert all("protocol" not in provider for provider in providers)
