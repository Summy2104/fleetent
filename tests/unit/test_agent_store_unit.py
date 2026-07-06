from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest

from fleetent import agent_store


class _Result:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
        lastrowid: int | None = None,
    ) -> None:
        self._row = row
        self._rows = rows or []
        self.lastrowid = lastrowid

    def fetchone(self) -> dict[str, Any] | None:
        return self._row

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Conn:
    def __init__(self, execute_impl) -> None:
        self._execute_impl = execute_impl

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _Result:
        return self._execute_impl(sql, params or {})


class _Db:
    def __init__(self, execute_impl) -> None:
        self._execute_impl = execute_impl

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _Result:
        return self._execute_impl(sql, params or {})

    @contextmanager
    def transaction(self):
        yield _Conn(self._execute_impl)


def _agent_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": 7,
        "name": "ops",
        "version": 2,
        "features": json.dumps({"code_execution": True}),
        "plugins": json.dumps(["github"]),
        "allowed_skills": json.dumps(["triage"]),
        "tenant_id": "tenant-1",
        "team_id": "team-1",
        "icon": "🤖",
        "config_overrides": json.dumps({"governance": {"strict": True}}),
        "supports_dm": 1,
        "supports_groups": 0,
        "system_prompt": "prompt",
        "allowed_tools": json.dumps(["shell"]),
        "skills_dir": "skills",
        "model_overrides": json.dumps({"default": "gpt"}),
        "memory_namespace": "ops",
    }
    row.update(overrides)
    return row


def test_parse_caps_and_validate_team_tenant() -> None:
    caps = agent_store._parse_caps(_agent_row())  # noqa: SLF001
    assert caps["features"]["code_execution"] is True
    assert caps["plugins"] == ["github"]
    assert caps["allowed_skills"] == ["triage"]
    assert caps["icon"] == "🤖"
    assert caps["supports_dm"] is True
    assert caps["supports_groups"] is False

    conn = _Conn(
        lambda sql, params: _Result(
            row={"tenant_id": "tenant-1"} if params["team_id"] == "team-1" else None
        )
    )
    agent_store._validate_team_tenant(
        conn, agent_name="ops", tenant_id="tenant-1", team_id="team-1"
    )  # noqa: SLF001
    with pytest.raises(ValueError, match="belongs to tenant"):
        agent_store._validate_team_tenant(  # noqa: SLF001
            conn,
            agent_name="ops",
            tenant_id="tenant-2",
            team_id="team-1",
        )


def test_row_to_agent_reads_current_state_fields() -> None:
    agent = agent_store._row_to_agent(  # noqa: SLF001
        _agent_row(), mcp_server_ids=["files", "github"]
    )
    assert agent.version == 2
    assert agent.system_prompt == "prompt"
    assert agent.allowed_tools == ["shell"]
    assert agent.mcp_server_ids == ["files", "github"]


def test_get_by_name_and_id_read_runtime_fields_from_agents_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def execute(sql: str, params: dict[str, Any]) -> _Result:
        if "FROM agents WHERE name" in sql:
            return _Result(row=_agent_row())
        if "FROM agents WHERE id" in sql:
            return _Result(row=_agent_row())
        if "SELECT server_id FROM agent_mcp_servers" in sql:
            return _Result(rows=[{"server_id": "files"}, {"server_id": "github"}])
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(execute))

    agent = agent_store.get_by_name("ops")
    assert agent is not None and agent.name == "ops"
    assert agent.version == 2
    assert agent.allowed_tools == ["shell"]
    assert agent.plugins == ["github"]
    assert agent.mcp_server_ids == ["files", "github"]

    by_id = agent_store.get_by_id(7)
    assert by_id is not None
    assert by_id.system_prompt == "prompt"
    assert by_id.memory_namespace == "ops"
    assert by_id.mcp_server_ids == ["files", "github"]


def test_get_by_name_returns_none_without_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_store, "_db", lambda: _Db(lambda sql, params: _Result(row=None)))
    assert agent_store.get_by_name("ops") is None

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        if "FROM agents WHERE name" in sql:
            return _Result(row=_agent_row())
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(execute))
    assert agent_store.get_by_name("ops") is not None


def test_update_agent_config_updates_agents_row_without_creating_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        calls.append((sql, params))
        if "FROM agents" in sql and "WHERE name = :name" in sql and "version" in sql:
            return _Result(
                row=_agent_row(
                    version=2,
                    tenant_id="tenant-1",
                    team_id="team-1",
                    system_prompt="updated",
                    allowed_tools=json.dumps(["shell", "read_file"]),
                    skills_dir="skills-next",
                    model_overrides=json.dumps({"default": "gpt-5"}),
                    memory_namespace="ops-next",
                    features=json.dumps({"code_execution": False}),
                    plugins=json.dumps(["jira"]),
                    allowed_skills=json.dumps(["triage", "deploy"]),
                    config_overrides=json.dumps({"governance": {"strict": False}}),
                )
            )
        if "SELECT tenant_id FROM teams WHERE id = :team_id" in sql:
            return _Result(row={"tenant_id": "tenant-1"})
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(execute))

    agent_store.update_agent_config(
        "ops",
        system_prompt="updated",
        allowed_tools=["shell", "read_file"],
        skills_dir="skills-next",
        mcp_server_ids=["github"],
        model_overrides={"default": "gpt-5"},
        memory_namespace="ops-next",
        features={"code_execution": False},
        plugins=["jira"],
        allowed_skills=["triage", "deploy"],
        tenant_id="tenant-1",
        team_id="team-1",
        config_overrides={"governance": {"strict": False}},
    )

    assert any("UPDATE agents SET" in sql for sql, _ in calls)
    assert any("DELETE FROM agent_mcp_servers" in sql for sql, _ in calls)
    assert any("INSERT OR IGNORE INTO agent_mcp_servers" in sql for sql, _ in calls)
    assert not any("INSERT INTO agent_versions" in sql for sql, _ in calls)


def test_create_agent_persists_current_state(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        calls.append((sql, params))
        if "SELECT 1 FROM agents" in sql:
            return _Result(row=None)
        if "INSERT INTO agents" in sql:
            return _Result(lastrowid=7)
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(execute))
    monkeypatch.setattr(agent_store, "_now", lambda: "2026-06-15T00:00:00+00:00")

    agent = agent_store.create_agent(
        "ops",
        "prompt",
        ["shell"],
        features={"code_execution": True},
        plugins=["github"],
        allowed_skills=["triage"],
        tenant_id="tenant-1",
        team_id="team-1",
        icon="🤖",
        config_overrides={"g": True},
    )
    assert agent.id == 7
    assert agent.version == 1

    def dup_execute(sql: str, params: dict[str, Any]) -> _Result:
        if "SELECT 1 FROM agents" in sql:
            return _Result(row={"1": 1})
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(dup_execute))
    with pytest.raises(ValueError, match="already exists"):
        agent_store.create_agent("ops", "prompt", ["shell"])


def test_versioning_entrypoints_removed() -> None:
    assert not hasattr(agent_store, "create_version")
    assert not hasattr(agent_store, "activate_version")
    assert not hasattr(agent_store, "list_versions")
    assert not hasattr(agent_store, "get_by_name_version")
    assert not hasattr(agent_store, "get_version_by_id")


def test_update_delete_and_lookup_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        calls.append((sql, params))
        if "FROM agents" in sql and "WHERE name = :name" in sql and "version" in sql:
            return _Result(row=_agent_row())
        if "SELECT id FROM agents WHERE name" in sql:
            return _Result(row={"id": 7})
        if "SELECT name FROM agents WHERE id" in sql:
            return _Result(row={"name": "ops"})
        if "SELECT name FROM agents ORDER BY name" in sql:
            return _Result(rows=[{"name": "alpha"}, {"name": "ops"}])
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(execute))
    hook_calls: list[int] = []
    monkeypatch.setattr(agent_store, "_delete_agent_hook", lambda aid: hook_calls.append(aid))

    agent_store.set_icon("ops", "🤖")
    agent_store.set_config_overrides("ops", {"g": True})
    agent_store.set_im_capabilities(7, supports_dm=True, supports_groups=False)
    assert agent_store.get_agent_name_by_id(7) == "ops"
    assert agent_store.list_all_names() == ["alpha", "ops"]
    assert agent_store.delete_agent("ops") is True
    assert hook_calls == [7]

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(lambda sql, params: _Result(row=None)))
    assert agent_store.delete_agent("missing") is False


def test_assignment_binding_and_default_agent_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        calls.append((sql, params))
        if "SELECT a.name FROM agents a JOIN user_agents" in sql:
            return _Result(row={"name": "ops"})
        if "SELECT user_id FROM user_agents" in sql:
            return _Result(rows=[{"user_id": "u1"}, {"user_id": "u2"}])
        if "FROM agent_im_groups" in sql:
            return _Result(rows=[{"platform": "slack", "group_id": "C1"}])
        if "SELECT server_id FROM agent_mcp_servers" in sql:
            return _Result(rows=[{"server_id": "files"}, {"server_id": "github"}])
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(execute))
    monkeypatch.setattr(agent_store, "_now", lambda: "2026-06-15T00:00:00+00:00")
    monkeypatch.setattr(
        agent_store,
        "get_by_name",
        lambda name: agent_store.Agent(id=7, name=name, system_prompt="p", allowed_tools=[]),
    )
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "ops")

    agent_store.assign_user("u1", 7)
    agent_store.unassign_user("u1", 7)
    assert agent_store.list_users_for_agent(7) == ["u1", "u2"]
    assert agent_store.list_im_groups_for_agent(7) == [{"platform": "slack", "group_id": "C1"}]
    agent_store.bind_mcp_server(7, "files", created_by="admin")
    agent_store.unbind_mcp_server(7, "files")
    assert agent_store.list_mcp_servers_for_agent(7) == ["files", "github"]
    assert agent_store.get_default_agent() is not None

    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: None)
    assert agent_store.get_default_agent() is None


def test_set_im_capabilities_updates_agent_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        calls.append((sql, params))
        return _Result()

    monkeypatch.setattr(agent_store, "_db", lambda: _Db(execute))

    agent_store.set_im_capabilities(7, supports_dm=True, supports_groups=False)

    assert calls == [
        (
            "UPDATE agents SET supports_dm = :supports_dm, supports_groups = :supports_groups "
            "WHERE id = :agent_id",
            {"supports_dm": 1, "supports_groups": 0, "agent_id": 7},
        )
    ]
