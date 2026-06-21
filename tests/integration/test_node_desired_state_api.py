from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)
    return db_path


@pytest.fixture
def node_client(db_path) -> TestClient:
    from fleetent.platform.node_management import node_desired_state_api

    app = FastAPI()
    app.include_router(node_desired_state_api.router)
    return TestClient(app)


def test_authenticate_node_request_enforces_node_key_and_url_scope(db_path) -> None:
    from fleetent.platform.node_management import node_store
    from fleetent.platform.node_management.node_desired_state_api import _authenticate_node_request

    node_a_key, _ = node_store.register_node("node-a")
    node_b_key, _ = node_store.register_node("node-b")
    _, user_key = user_store.create_user("alice")

    identity = _authenticate_node_request("node-a", f"Bearer {node_a_key}")
    assert identity["id"] == "node-a"

    with pytest.raises(HTTPException, match="Invalid node API key") as invalid_exc:
        _authenticate_node_request("node-a", "Bearer ma-" + "0" * 64)
    assert invalid_exc.value.status_code == 401

    with pytest.raises(HTTPException, match="Invalid node API key") as user_exc:
        _authenticate_node_request("node-a", f"Bearer {user_key}")
    assert user_exc.value.status_code == 401

    with pytest.raises(HTTPException, match="forbidden") as forbidden_exc:
        _authenticate_node_request("node-b", f"Bearer {node_a_key}")
    assert forbidden_exc.value.status_code == 403

    identity = _authenticate_node_request("node-b", f"Bearer {node_b_key}")
    assert identity["id"] == "node-b"


def test_platform_user_bearer_rejects_node_service_key(db_path) -> None:
    from fleetent.platform.node_management import node_store
    from fleetent.platform.user_management.platform_bearer_adapter import PlatformBearerAdapter

    node_key, _ = node_store.register_node("node-a")

    assert PlatformBearerAdapter()(node_key) is None


def test_get_desired_state_returns_only_enabled_agents_for_node(node_client: TestClient) -> None:
    from fleetent import agent_store
    from fleetent.platform.agent_management_console import agent_admin_store
    from fleetent.platform.model_provider_management import provider_admin_store
    from fleetent.platform.node_management import node_store, placement_store

    node_key, _ = node_store.register_node("node-a")
    node_store.register_node("node-b")
    provider_admin_store.add_provider(
        "claude-fast",
        "https://api.anthropic.com/v1/",
        "claude-haiku-4-5-20251001",
        provider="anthropic",
        protocol="openai_chat",
        api_key="sk-inline-secret",
        api_key_env="FLEETENT_AGENT_ENABLED_MODEL",
    )

    enabled = agent_store.create_agent(
        "enabled",
        "Help users",
        ["shell"],
        model_overrides={"default": [{"provider_id": "claude-fast"}]},
        config_overrides={
            "im": {
                "slack": {
                    "bot_token_env": "ENABLED_SLACK_BOT",
                    "app_token_env": "ENABLED_SLACK_APP",
                },
            }
        },
    )
    disabled = agent_store.create_agent("disabled", "Disabled agent", ["shell"])
    archived = agent_store.create_agent("archived", "Archived agent", ["shell"])
    other_node = agent_store.create_agent("other-node", "Other node", ["shell"])

    placement_store.pin_agent(enabled.id, "node-a")
    placement_store.pin_agent(disabled.id, "node-a")
    placement_store.pin_agent(archived.id, "node-a")
    placement_store.pin_agent(other_node.id, "node-b")

    agent_admin_store.disable(disabled.id)
    agent_admin_store.archive(archived.id)
    agent_store.set_im_capabilities("enabled", supports_dm=True, supports_groups=False)

    response = node_client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["node_id"] == "node-a"
    assert [agent["name"] for agent in payload["agents"]] == ["enabled"]
    config = payload["agents"][0]["config"]
    assert config["name"] == "enabled"
    assert config["system_prompt"] == "Help users"
    assert config["models"]["targets"][0]["api_key_env"] == "FLEETENT_AGENT_ENABLED_MODEL"
    assert config["im"]["supports_dm"] is True
    assert config["im"]["slack"]["bot_token_env"] == "ENABLED_SLACK_BOT"
    assert config["im"]["slack"]["app_token_env"] == "ENABLED_SLACK_APP"
    assert "sk-inline-secret" not in str(config)


def test_get_desired_state_returns_empty_agent_set_when_node_has_no_enabled_placements(
    node_client: TestClient,
) -> None:
    from fleetent import agent_store
    from fleetent.platform.agent_management_console import agent_admin_store
    from fleetent.platform.node_management import node_store, placement_store

    node_key, _ = node_store.register_node("node-a")
    disabled = agent_store.create_agent("disabled", "Disabled agent", ["shell"])
    placement_store.pin_agent(disabled.id, "node-a")
    agent_admin_store.disable(disabled.id)

    response = node_client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )

    assert response.status_code == 200
    assert response.json() == {"node_id": "node-a", "agents": []}


def test_get_desired_state_includes_only_set_secrets_for_enabled_agents_on_target_node(
    node_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import agent_store
    from fleetent.platform.agent_lifecycle import credential_slots, secret_store
    from fleetent.platform.agent_management_console import agent_admin_store
    from fleetent.platform.node_management import node_store, placement_store

    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"4" * 32).decode("ascii"),
    )
    node_key, _ = node_store.register_node("node-a")
    node_store.register_node("node-b")
    enabled = agent_store.create_agent(
        "enabled",
        "Help users",
        ["shell"],
        config_overrides={
            "im": {
                "slack": {
                    "bot_token_env": "ENABLED_SLACK_BOT",
                    "app_token_env": "ENABLED_SLACK_APP",
                }
            }
        },
    )
    other_node = agent_store.create_agent("other-node", "Other node", ["shell"])
    disabled = agent_store.create_agent("disabled", "Disabled agent", ["shell"])

    placement_store.pin_agent(enabled.id, "node-a")
    placement_store.pin_agent(other_node.id, "node-b")
    placement_store.pin_agent(disabled.id, "node-a")
    agent_admin_store.disable(disabled.id)

    credential_slots.ensure_slot(
        enabled,
        "env:ENABLED_SLACK_BOT",
        mode="inject",
        env_name="ENABLED_SLACK_BOT",
    )
    credential_slots.ensure_slot(
        enabled,
        "env:ENABLED_SLACK_APP",
        mode="inject",
        env_name="ENABLED_SLACK_APP",
    )
    credential_slots.ensure_slot(
        other_node,
        "env:OTHER_NODE_SECRET",
        mode="inject",
        env_name="OTHER_NODE_SECRET",
    )
    credential_slots.ensure_slot(
        disabled,
        "env:DISABLED_SECRET",
        mode="inject",
        env_name="DISABLED_SECRET",
    )
    secret_store.set(enabled.id, "ENABLED_SLACK_BOT", "xoxb-live-secret", "admin")
    secret_store.set(other_node.id, "OTHER_NODE_SECRET", "other-node-secret", "admin")
    secret_store.set(disabled.id, "DISABLED_SECRET", "disabled-secret", "admin")

    response = node_client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["node_id"] == "node-a"
    assert [agent["name"] for agent in payload["agents"]] == ["enabled"]
    delivered = payload["agents"][0]
    assert delivered["secrets"] == {"ENABLED_SLACK_BOT": "xoxb-live-secret"}
    assert delivered["config"]["im"]["slack"]["access"]["require_approval"] is True
    assert delivered["config"]["im"]["slack"]["bot_token_env"] == "ENABLED_SLACK_BOT"
    assert delivered["config"]["im"]["slack"]["app_token_env"] == "ENABLED_SLACK_APP"
    assert "ENABLED_SLACK_APP" not in delivered["secrets"]
    assert "other-node-secret" not in str(payload)
    assert "disabled-secret" not in str(payload)


def test_post_status_updates_last_seen_and_agent_projection(node_client: TestClient) -> None:
    from fleetent import agent_store
    from fleetent.platform.node_management import node_store

    node_key, _ = node_store.register_node("node-a")
    agent = agent_store.create_agent("enabled", "Help users", ["shell"])

    response = node_client.post(
        "/nodes/node-a/status",
        headers={"Authorization": f"Bearer {node_key}"},
        json={
            "agents": [
                {
                    "agent_id": agent.id,
                    "phase": "running",
                    "pid": 1234,
                    "health": "ok",
                    "detail": "ready",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"node_id": "node-a", "updated": 1}
    node = node_store.get_node("node-a")
    assert node is not None
    assert node["last_seen_at"] is not None
    statuses = node_store.list_agent_status_by_node("node-a")
    assert statuses == [
        {
            "agent_id": agent.id,
            "node_id": "node-a",
            "phase": "running",
            "pid": 1234,
            "health": "ok",
            "detail": "ready",
            "reported_at": statuses[0]["reported_at"],
        }
    ]


def test_post_status_enforces_node_auth_scope(node_client: TestClient) -> None:
    from fleetent.platform.node_management import node_store

    node_a_key, _ = node_store.register_node("node-a")
    node_store.register_node("node-b")
    _, user_key = user_store.create_user("alice")

    forbidden = node_client.post(
        "/nodes/node-b/status",
        headers={"Authorization": f"Bearer {node_a_key}"},
        json={"agents": []},
    )
    assert forbidden.status_code == 403

    unauthorized = node_client.post(
        "/nodes/node-a/status",
        headers={"Authorization": f"Bearer {user_key}"},
        json={"agents": []},
    )
    assert unauthorized.status_code == 401
