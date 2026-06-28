"""Integration tests for split provider/model admin APIs."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.model_provider_management.model_admin_api as model_api
import fleetent.platform.model_provider_management.provider_admin_api as provider_api
import fleetent.platform.model_provider_management.provider_admin_store as provider_store
import fleetent.user_store as user_store
from fleetent.db import create_database
from tests.integration._migration_template import apply_migrations


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("db_ro")
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    db_instance = create_database(f"sqlite:///{db_path}")
    mp.setattr(user_store, "_db", lambda: db_instance)
    mp.setattr(provider_store, "_database", lambda: db_instance)
    mp.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    app = FastAPI()
    app.include_router(provider_api.router)
    app.include_router(model_api.router)
    yield TestClient(app, raise_server_exceptions=True)
    mp.undo()


@pytest.fixture
def fresh_client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    db_instance = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(user_store, "_db", lambda: db_instance)
    monkeypatch.setattr(provider_store, "_database", lambda: db_instance)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    app = FastAPI()
    app.include_router(provider_api.router)
    app.include_router(model_api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Session {token}"}


def _add_provider(client: TestClient, token: str, provider_id: str = "openai", **kw):
    body = {"id": provider_id, "provider": "openai", "base_url": "https://api.openai.com/v1", **kw}
    return client.post("/admin/providers", headers=_hdr(token), json=body)


def _add_model(client: TestClient, token: str, model_id: str = "gpt-5", **kw):
    body = {
        "id": model_id,
        "provider_id": "openai",
        "protocol": "openai_chat",
        "model_name": "gpt-5",
        "base_url": "https://api.openai.com/v1",
        **kw,
    }
    return client.post("/admin/models", headers=_hdr(token), json=body)


def test_no_auth_401(client):
    assert client.get("/admin/providers").status_code == 401
    assert client.get("/admin/models").status_code == 401


def test_viewer_cannot_write_provider_or_model(client):
    token, _ = _session_for("viewer")
    assert _add_provider(client, token).status_code == 403
    assert _add_model(client, token).status_code == 403


def test_provider_crud_is_provider_only_and_masks_key(fresh_client):
    token, _ = _session_for("admin")
    created = _add_provider(
        fresh_client,
        token,
        api_key="sk-secret",
        api_key_env="OPENAI_API_KEY",
        description="shared openai",
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["api_key"] == "****"
    assert body["api_key_set"] is True
    assert body["provider"] == "openai"
    assert body["base_url"] == "https://api.openai.com/v1"
    assert "model" not in body

    listed = fresh_client.get("/admin/providers", headers=_hdr(token))
    assert listed.status_code == 200
    assert listed.json()[0]["model_count"] == 0
    assert "model" not in listed.json()[0]

    edited = fresh_client.put(
        "/admin/providers/openai",
        headers=_hdr(token),
        json={"base_url": "https://new.example/v1"},
    )
    assert edited.status_code == 200
    assert edited.json()["base_url"] == "https://new.example/v1"
    assert provider_store.get_provider("openai")["api_key"] == "sk-secret"


def test_provider_body_rejects_model_fields(fresh_client):
    token, _ = _session_for("admin")
    response = fresh_client.post(
        "/admin/providers",
        headers=_hdr(token),
        json={
            "id": "bad",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5",
        },
    )
    assert response.status_code == 422


def test_delete_provider_with_models_conflicts(fresh_client):
    token, _ = _session_for("admin")
    assert _add_provider(fresh_client, token).status_code == 200
    assert _add_model(fresh_client, token).status_code == 200

    response = fresh_client.delete("/admin/providers/openai", headers=_hdr(token))
    assert response.status_code == 409


def test_model_crud_and_connectivity_test(fresh_client, monkeypatch):
    monkeypatch.setattr(
        model_api,
        "router_connectivity_test",
        lambda model, provider: {
            "reachable": True,
            "latency_ms": 42,
            "model": model["model_name"],
            "provider_id": provider["id"],
        },
    )
    token, _ = _session_for("admin")
    assert _add_provider(fresh_client, token, api_key="sk-secret").status_code == 200

    created = _add_model(
        fresh_client,
        token,
        max_tokens=4096,
        params={"temperature": 0.2},
    )
    assert created.status_code == 200, created.text
    assert created.json()["provider_id"] == "openai"
    assert created.json()["model_name"] == "gpt-5"
    assert "api_key" not in created.json()

    listed = fresh_client.get("/admin/models", headers=_hdr(token))
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == "gpt-5"

    edited = fresh_client.put(
        "/admin/models/gpt-5",
        headers=_hdr(token),
        json={"base_url": "https://new-model.example/v1"},
    )
    assert edited.status_code == 200
    assert edited.json()["base_url"] == "https://new-model.example/v1"

    connectivity = fresh_client.post("/admin/models/gpt-5/connectivity-test", headers=_hdr(token))
    assert connectivity.status_code == 200
    assert connectivity.json()["reachable"] is True
    assert connectivity.json()["model"] == "gpt-5"


def test_model_endpoint_validates_protocol_specific_connection_fields(fresh_client):
    token, _ = _session_for("admin")
    assert _add_provider(fresh_client, token).status_code == 200

    response = fresh_client.post(
        "/admin/models",
        headers=_hdr(token),
        json={
            "id": "embed-3",
            "provider_id": "openai",
            "protocol": "http_embedding",
            "model_name": "text-embedding-3-small",
            "base_url": "https://wrong.example/v1",
        },
    )
    assert response.status_code == 422


def test_delete_provider_audits_when_no_models(fresh_client):
    token, _ = _session_for("admin")
    assert _add_provider(fresh_client, token, provider_id="solo").status_code == 200
    response = fresh_client.delete("/admin/providers/solo", headers=_hdr(token))
    assert response.status_code == 200
    assert provider_store.get_provider("solo") is None
    assert any(entry["action"] == "provider.delete" for entry in audit.search_audit())


def test_model_and_provider_references_include_legacy_override_shapes(fresh_client):
    token, _ = _session_for("admin")
    assert _add_provider(fresh_client, token).status_code == 200
    assert _add_model(fresh_client, token, model_id="gpt-5").status_code == 200
    assert (
        _add_model(
            fresh_client,
            token,
            model_id="text-embed-3",
            protocol="http_embedding",
            model_name="text-embedding-3-small",
            base_url=None,
            endpoint="https://embed.example/v1/embeddings",
        ).status_code
        == 200
    )
    agent_store.create_agent(
        "new-shape",
        "prompt",
        [],
        model_overrides={"routes": {"default": [{"model_id": "gpt-5"}]}},
    )
    agent_store.create_agent(
        "legacy-shape",
        "prompt",
        [],
        model_overrides={"default": [{"provider_id": "text-embed-3"}]},
    )

    model_refs = fresh_client.get("/admin/models/gpt-5/references", headers=_hdr(token))
    assert model_refs.status_code == 200
    assert model_refs.json() == {"agents": ["new-shape"], "models": ["gpt-5"]}

    provider_refs = fresh_client.get("/admin/providers/openai/references", headers=_hdr(token))
    assert provider_refs.status_code == 200
    assert provider_refs.json() == {
        "agents": ["legacy-shape", "new-shape"],
        "models": ["gpt-5", "text-embed-3"],
    }


def test_delete_model_conflicts_when_referenced_by_agent(fresh_client):
    token, _ = _session_for("admin")
    assert _add_provider(fresh_client, token).status_code == 200
    assert _add_model(fresh_client, token, model_id="gpt-5").status_code == 200
    agent_store.create_agent(
        "bound-agent",
        "prompt",
        [],
        model_overrides={"routes": {"default": [{"model_id": "gpt-5"}]}},
    )

    response = fresh_client.delete("/admin/models/gpt-5", headers=_hdr(token))
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "model still referenced",
        "agents": ["bound-agent"],
        "models": ["gpt-5"],
    }


def test_temperature_is_rejected_in_authoring_bodies_and_connectivity_ignores_it(
    fresh_client, monkeypatch
):
    payloads: list[dict[str, object]] = []

    monkeypatch.setattr(
        model_api,
        "test_provider_connectivity_sync",
        lambda payload: payloads.append(payload) or {"reachable": True},
    )
    token, _ = _session_for("admin")

    provider_with_temperature = fresh_client.post(
        "/admin/providers",
        headers=_hdr(token),
        json={
            "id": "bad-provider",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.2,
        },
    )
    assert provider_with_temperature.status_code == 422

    assert _add_provider(fresh_client, token).status_code == 200
    model_with_temperature = fresh_client.post(
        "/admin/models",
        headers=_hdr(token),
        json={
            "id": "bad-model",
            "provider_id": "openai",
            "protocol": "openai_chat",
            "model_name": "gpt-5",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.2,
        },
    )
    assert model_with_temperature.status_code == 422

    assert (
        _add_model(
            fresh_client,
            token,
            model_id="connectivity-model",
            params={"temperature": 0.2},
        ).status_code
        == 200
    )
    response = fresh_client.post(
        "/admin/models/connectivity-model/connectivity-test",
        headers=_hdr(token),
    )
    assert response.status_code == 200
    assert payloads == [
        {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5",
            "api_key": None,
        }
    ]
