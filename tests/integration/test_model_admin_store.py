"""Integration tests for model_admin_store on split providers/models tables."""

import pytest

from fleetent.platform.model_provider_management import model_admin_store, provider_admin_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_add_and_get_model(store_db):
    provider_admin_store.add_provider("openai", provider="openai", api_key_env="OPENAI_API_KEY")

    model_admin_store.add_model(
        "gpt-5",
        provider_id="openai",
        protocol="openai_chat",
        model_name="gpt-5",
        base_url="https://api.openai.example/v1",
        max_tokens=4096,
        params={"reasoning_effort": "medium"},
        extra_params={"top_p": 0.9},
        description="chat default",
    )

    model = model_admin_store.get_model("gpt-5")

    assert model is not None
    assert model["provider_id"] == "openai"
    assert model["protocol"] == "openai_chat"
    assert model["model_name"] == "gpt-5"
    assert model["base_url"] == "https://api.openai.example/v1"
    assert model["max_tokens"] == 4096
    assert model["params"] == {"reasoning_effort": "medium"}
    assert model["extra_params"] == {"top_p": 0.9}


def test_list_models_filters_by_provider_and_protocol(store_db):
    provider_admin_store.add_provider("openai", provider="openai")
    provider_admin_store.add_provider("voyage", provider="voyage")
    model_admin_store.add_model(
        "gpt-5", provider_id="openai", protocol="openai_chat", model_name="gpt-5"
    )
    model_admin_store.add_model(
        "text-embedding-3-small",
        provider_id="openai",
        protocol="http_embedding",
        model_name="text-embedding-3-small",
        endpoint="https://api.openai.example/embeddings",
    )
    model_admin_store.add_model(
        "voyage-3", provider_id="voyage", protocol="http_embedding", model_name="voyage-3"
    )

    assert {model["id"] for model in model_admin_store.list_models(provider_id="openai")} == {
        "gpt-5",
        "text-embedding-3-small",
    }
    assert {model["id"] for model in model_admin_store.list_models(protocol="http_embedding")} == {
        "text-embedding-3-small",
        "voyage-3",
    }


def test_edit_and_delete_model(store_db):
    provider_admin_store.add_provider("anthropic", provider="anthropic")
    model_admin_store.add_model(
        "claude-sonnet",
        provider_id="anthropic",
        protocol="openai_chat",
        model_name="claude-sonnet",
    )

    model_admin_store.edit_model(
        "claude-sonnet",
        base_url="https://api.anthropic.example/v1",
        params={"temperature": 0.1},
    )
    edited = model_admin_store.get_model("claude-sonnet")
    assert edited is not None
    assert edited["base_url"] == "https://api.anthropic.example/v1"
    assert edited["params"] == {"temperature": 0.1}

    model_admin_store.delete_model("claude-sonnet")
    assert model_admin_store.get_model("claude-sonnet") is None
