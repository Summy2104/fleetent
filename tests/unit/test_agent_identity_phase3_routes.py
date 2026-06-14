from __future__ import annotations

from types import SimpleNamespace

from fleetent.platform.askit_console import agent_apply_api
from fleetent.platform.chat_management import chat_admin_api
from fleetent.server import agent_routing_status


def test_agent_routing_status_resolves_name_to_id(monkeypatch) -> None:
    captured: dict[str, int] = {}

    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fleetent")
    monkeypatch.setattr("fleetent.server.agent_store.get_by_name", lambda name: SimpleNamespace(id=7))

    def get_state(agent_id: int) -> dict[str, str]:
        captured["agent_id"] = agent_id
        return {"status": "disabled"}

    monkeypatch.setattr(
        "fleetent.platform.agent_management_console.agent_admin_store.get_state",
        get_state,
    )

    assert agent_routing_status("ops") == "disabled"
    assert captured == {"agent_id": 7}


def test_playground_start_persists_agent_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    actor = SimpleNamespace(id="admin-1", role="admin")
    monkeypatch.setattr(chat_admin_api, "_require_admin", lambda authorization: actor)
    monkeypatch.setattr(
        chat_admin_api.agent_store,
        "get_by_name",
        lambda name: SimpleNamespace(id=11, name=name),
    )

    def upsert_meta(session_id: str, **kwargs: object) -> None:
        captured["session_id"] = session_id
        captured.update(kwargs)

    monkeypatch.setattr(chat_admin_api.session_admin_store, "upsert_meta", upsert_meta)

    started = chat_admin_api.playground_start(chat_admin_api.StartBody(agent_name="ops"), "Session t")

    assert started["agent_name"] == "ops"
    assert captured["origin"] == "playground"
    assert captured["agent_id"] == 11


def test_apply_one_resolves_name_to_agent_id_for_provenance(monkeypatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        agent_apply_api,
        "get_agent_def",
        lambda name: {"id": 13, "system_prompt": "old", "allowed_tools": ["shell"]},
    )
    monkeypatch.setattr(
        agent_apply_api,
        "update_agent_def",
        lambda name, system_prompt, allowed_tools: seen.update(updated=name),
    )

    def get_state(agent_id: int) -> dict[str, str]:
        seen["get_state_agent_id"] = agent_id
        return {"provenance": "adhoc"}

    def set_provenance(agent_id: int, provenance: str) -> None:
        seen["set_provenance"] = (agent_id, provenance)

    monkeypatch.setattr(agent_apply_api.agent_admin_store, "get_state", get_state)
    monkeypatch.setattr(agent_apply_api.agent_admin_store, "set_provenance", set_provenance)

    result = agent_apply_api._apply_one(
        agent_apply_api.AgentSpec(name="ops", system_prompt="new", allowed_tools=["shell"]),
        "admin-1",
    )

    assert result["action"] == "adopted"
    assert seen["get_state_agent_id"] == 13
    assert seen["set_provenance"] == (13, "managed")
