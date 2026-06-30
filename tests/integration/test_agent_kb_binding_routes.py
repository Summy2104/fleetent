"""Integration tests for agent/KB binding routes keyed by integer agent ids."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fleetent import agent_store, auth, user_store
from fleetent.db import create_database
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.agent_management_console import agent_admin_api
from fleetent.platform.knowledge_base_management import agent_kbs_store, kb_admin_api
from tests.integration._migration_template import apply_migrations


def _patch_stores(monkeypatch, db_path) -> None:
    db_instance = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(user_store, "_db", lambda: db_instance)
    monkeypatch.setattr(agent_store, "_db", lambda: db_instance)
    monkeypatch.setattr(agent_kbs_store, "_database", lambda: db_instance)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")


def _session_for(role: str) -> tuple[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    return auth.create_session(user.id), user.id


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Session {token}"}


def test_agent_and_kb_routes_materialize_same_integer_binding_set(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    _patch_stores(monkeypatch, db_path)
    monkeypatch.setattr(kb_admin_api, "kb_engine_list", lambda tenant_id: [])

    app = FastAPI()
    app.include_router(agent_admin_api.router)
    app.include_router(kb_admin_api.router)
    client = TestClient(app, raise_server_exceptions=True)

    agent = agent_store.create_agent("support", "Support.", ["shell"])
    token, _ = _session_for("admin")

    agent_resp = client.post(
        "/admin/agents/support/kbs", headers=_hdr(token), json={"kb_id": "kb1"}
    )
    assert agent_resp.status_code == 200

    kb_resp = client.post("/admin/kb/kb2/agents", headers=_hdr(token), json={"agent_id": agent.id})
    assert kb_resp.status_code == 200

    assert agent_kbs_store.list_kbs_for_agent("default", agent.id) == ["kb1", "kb2"]
    assert client.get(f"/admin/kb/by-agent/{agent.id}", headers=_hdr(token)).json() == {
        "agent_id": agent.id,
        "kb_ids": ["kb1", "kb2"],
    }
    assert client.get("/admin/kb/kb2/agents", headers=_hdr(token)).json() == {
        "kb_id": "kb2",
        "agents": [agent.id],
    }
    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))
    assert [binding.kb_id for binding in exported.knowledge.bindings] == ["kb1", "kb2"]
