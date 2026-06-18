from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.platform.agent_lifecycle.materialize as materialize
import fleetent.platform.agent_management_console.agent_admin_api as api
import fleetent.platform.agent_management_console.agent_admin_store as agent_admin_store
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    apply_migrations(db_path)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_header(role: str) -> dict[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    token = auth.create_session(user.id)
    return {"Authorization": f"Session {token}"}


def test_default_agent_routes_exist(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.put("/admin/agents/basic/default")

    assert response.status_code != 404


def test_set_default_clears_previous(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    basic = agent_store.create_agent("basic", "Basic.", ["shell"])
    ops = agent_store.create_agent("ops", "Ops.", ["shell"])
    agent_admin_store.enable(ops.id)

    first = client.put("/admin/agents/ops/default", headers=_session_header("admin"))
    second = client.put("/admin/agents/basic/default", headers=_session_header("admin"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert agent_admin_store.get_state(basic.id)["is_default"] == 1
    assert agent_admin_store.get_state(ops.id)["is_default"] == 0


def test_materialize_emits_bindings_default(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path / "home"))
    apply_migrations(db_path)
    agent = agent_store.create_agent("basic", "Basic.", ["shell"])
    agent_admin_store.set_default(agent.id)

    payload = materialize.agent_file_from_store(agent).model_dump(
        mode="json", exclude_defaults=False
    )

    assert payload["bindings"]["default"] is True
