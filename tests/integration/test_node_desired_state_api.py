from __future__ import annotations

import base64
import datetime
import hashlib
import io
import tarfile

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
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


def test_get_desired_state_exports_knowledge_bindings_without_source_construction(
    node_client: TestClient,
) -> None:
    from fleetent import agent_store
    from fleetent.platform.knowledge_base_management import agent_kbs_store
    from fleetent.platform.node_management import node_store, placement_store
    from fleetent.platform.tenancy import store as tenancy_store

    tenancy_store.create_tenant(id="acme", name="Acme")
    node_key, _ = node_store.register_node("node-a")
    agent = agent_store.create_agent("support", "Help users", ["shell"], tenant_id="acme")
    agent_kbs_store.bind("acme", "support-kb", agent.id, created_by="admin")
    placement_store.pin_agent(agent.id, "node-a")

    response = node_client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )

    assert response.status_code == 200
    delivered = response.json()["agents"][0]
    assert delivered["tenant_id"] == "acme"
    binding = delivered["config"]["knowledge"]["bindings"][0]
    assert binding["tenant_id"] == "acme"
    assert binding["kb_id"] == "support-kb"
    assert binding["default"] is True
    assert "google_drive" not in str(delivered["config"])
    assert "confluence" not in str(delivered["config"])


def test_get_desired_state_marks_kb_binding_changes_for_resync(node_client: TestClient) -> None:
    import fleetent.auth as auth
    from fleetent import agent_store
    from fleetent.platform.agent_management_console import agent_admin_api
    from fleetent.platform.node_management import node_store, placement_store
    from fleetent.platform.tenancy import store as tenancy_store

    tenancy_store.create_tenant(id="acme", name="Acme")
    node_key, _ = node_store.register_node("node-a")
    agent = agent_store.create_agent("support", "Help users", ["shell"], tenant_id="acme")
    placement_store.pin_agent(agent.id, "node-a")
    admin_user, _ = user_store.create_user("admin-user")
    user_store.set_role(admin_user.id, "admin")
    admin_session = auth.create_session(admin_user.id)
    app = FastAPI()
    app.include_router(agent_admin_api.router)
    app.include_router(node_client.app.router)
    client = TestClient(app)

    before = client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )
    assert before.status_code == 200
    initial_epoch = before.json()["agents"][0]["knowledge_resync_epoch"]

    bind_resp = client.post(
        "/admin/agents/support/kbs",
        headers={"Authorization": f"Session {admin_session}"},
        json={"kb_id": "support-kb"},
    )
    assert bind_resp.status_code == 200
    after_bind = client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )
    assert after_bind.status_code == 200
    bind_epoch = after_bind.json()["agents"][0]["knowledge_resync_epoch"]

    unbind_resp = client.delete(
        "/admin/agents/support/kbs/support-kb",
        headers={"Authorization": f"Session {admin_session}"},
    )
    assert unbind_resp.status_code == 200
    after_unbind = client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )
    assert after_unbind.status_code == 200
    unbind_epoch = after_unbind.json()["agents"][0]["knowledge_resync_epoch"]

    assert bind_epoch != initial_epoch
    assert unbind_epoch != bind_epoch


def test_get_desired_state_includes_skill_manifest_and_bundle_download_is_immutable(
    node_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from fleetent import agent_store
    from fleetent.platform.node_management import node_store, placement_store
    from fleetent.platform.skill_management import pool_git, skill_admin_store
    from fleetent.platform.tenancy import store as tenancy_store

    pool_dir = tmp_path / "skills-pool"
    skill_dir = pool_dir / "incident-review"
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: Review incidents\n---\nbody\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
    (skill_dir / ".git").mkdir()
    (skill_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(pool_dir))
    pool_git.init_pool(pool_dir)

    node_key, _ = node_store.register_node("node-a")
    tenancy_store.create_tenant(id="acme", name="Acme")
    agent = agent_store.create_agent("support", "Help users", ["shell"], tenant_id="acme")
    skill_admin_store.set_binding(agent.id, "incident-review", True, updated_by="admin")
    placement_store.pin_agent(agent.id, "node-a")

    response = node_client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )

    assert response.status_code == 200
    manifest = response.json()["agents"][0]["skill_manifests"][0]
    assert manifest["name"] == "incident-review"
    assert manifest["base_version"]
    assert manifest["base_commit"]
    assert manifest["bundle_url"].endswith(
        f"/nodes/node-a/skills/incident-review/bundles/{manifest['base_version']}.tar.gz"
    )
    assert "Review incidents" not in str(manifest)

    first = node_client.get(
        manifest["bundle_url"],
        headers={"Authorization": f"Bearer {node_key}"},
    )
    assert first.status_code == 200
    assert hashlib.sha256(first.content).hexdigest() == manifest["bundle_sha256"]
    with tarfile.open(fileobj=io.BytesIO(first.content), mode="r:gz") as archive:
        assert sorted(archive.getnames()) == [
            "incident-review/SKILL.md",
            "incident-review/scripts/helper.py",
        ]

    (skill_dir / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: Review incidents\n---\nchanged\n",
        encoding="utf-8",
    )
    pool_git.commit_pool(
        pool_dir,
        message="edit: mutate pool skill after cache",
        author="test <test@fleetent>",
        skill_name="incident-review",
    )

    second = node_client.get(
        manifest["bundle_url"],
        headers={"Authorization": f"Bearer {node_key}"},
    )
    assert second.status_code == 200
    assert second.content == first.content


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


def test_post_status_projects_skill_drift_to_agent_skills(
    node_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import agent_store
    from fleetent.platform.node_management import node_store
    from fleetent.platform.skill_management import backflow_store, skill_admin_store

    node_key, _ = node_store.register_node("node-a")
    agent = agent_store.create_agent("enabled", "Help users", ["shell"])
    skill_admin_store.set_binding(agent.id, "incident-review", True, updated_by="admin")
    nominations: list[tuple[int, str]] = []
    original_nominate = backflow_store.nominate_if_absent

    def _record_nomination(*, agent_id: int, skill_name: str, pool_dir):
        nominations.append((agent_id, skill_name))
        return original_nominate(agent_id=agent_id, skill_name=skill_name, pool_dir=pool_dir)

    monkeypatch.setattr(backflow_store, "nominate_if_absent", _record_nomination)

    response = node_client.post(
        "/nodes/node-a/status",
        headers={"Authorization": f"Bearer {node_key}"},
        json={
            "agents": [
                {
                    "agent_id": agent.id,
                    "phase": "running",
                    "skills": [
                        {
                            "skill_name": "incident-review",
                            "base_version": "abc123",
                            "base_commit": "def456",
                            "drift": True,
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    drift = skill_admin_store.get_drift(agent.id, "incident-review")
    assert drift["base_version"] == "abc123"
    assert drift["base_commit"] == "def456"
    assert drift["drift"] == 1
    assert nominations == [(agent.id, "incident-review")]


def test_post_identity_resolve_returns_resolve_or_provision_principal(
    node_client: TestClient,
) -> None:
    from fleetent.platform.im_gateway_management.identity import resolve_or_provision
    from fleetent.platform.node_management import node_store
    from fleetent.platform.tenancy import store as tenancy_store

    node_key, _ = node_store.register_node("node-a")
    tenancy_store.create_tenant(id="tenant-1", name="Tenant 1")
    expected = resolve_or_provision(
        "tenant-1",
        verified_email="alice@example.com",
        channel="slack",
        platform_user_id="U123",
    )

    response = node_client.post(
        "/nodes/node-a/identity/resolve",
        headers={"Authorization": f"Bearer {node_key}"},
        json={
            "tenant_id": "tenant-1",
            "channel": "slack",
            "platform_user_id": "U123",
            "verified_email": "alice@example.com",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": expected.id, "tenant_id": expected.tenant_id}


@pytest.mark.parametrize(
    ("authorization", "expected_status"),
    [
        (None, 401),
        ("Bearer ma-" + "0" * 64, 401),
    ],
)
def test_post_identity_resolve_rejects_missing_or_invalid_node_key(
    node_client: TestClient,
    authorization: str | None,
    expected_status: int,
) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-a")
    headers = {} if authorization is None else {"Authorization": authorization}

    response = node_client.post(
        "/nodes/node-a/identity/resolve",
        headers=headers,
        json={
            "tenant_id": "tenant-1",
            "channel": "slack",
            "platform_user_id": "U123",
        },
    )

    assert response.status_code == expected_status


def test_post_identity_resolve_rejects_node_key_for_other_node(node_client: TestClient) -> None:
    from fleetent.platform.node_management import node_store

    node_a_key, _ = node_store.register_node("node-a")
    node_store.register_node("node-b")

    response = node_client.post(
        "/nodes/node-b/identity/resolve",
        headers={"Authorization": f"Bearer {node_a_key}"},
        json={
            "tenant_id": "tenant-1",
            "channel": "slack",
            "platform_user_id": "U123",
        },
    )

    assert response.status_code == 403


def test_post_link_confirm_attaches_pending_identity_and_writes_audit(
    node_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.platform.im_gateway_management.pending_link_store import PendingLinkStore
    from fleetent.platform.node_management import node_desired_state_api, node_store
    from fleetent.platform.tenancy import store as tenancy_store

    tenancy_store.create_tenant(id="tenant-1", name="Tenant 1")
    user, _ = user_store.create_user("Alice", email="alice@example.com", tenant_id="tenant-1")
    store = PendingLinkStore(ttl=datetime.timedelta(minutes=10))
    store.put("link-code", user_id=user.id, tenant_id="tenant-1")
    monkeypatch.setattr(node_desired_state_api, "_pending_links", store)
    audits: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        node_desired_state_api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args)
    )
    node_key, _ = node_store.register_node("node-a")

    response = node_client.post(
        "/nodes/node-a/link-confirm",
        headers={"Authorization": f"Bearer {node_key}"},
        json={
            "platform": "telegram",
            "platform_user_id": "424242",
            "code": "link-code",
        },
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == user.id
    assert audits


def test_post_link_confirm_rejects_invalid_code(node_client: TestClient) -> None:
    from fleetent.platform.node_management import node_store

    node_key, _ = node_store.register_node("node-a")
    response = node_client.post(
        "/nodes/node-a/link-confirm",
        headers={"Authorization": f"Bearer {node_key}"},
        json={
            "platform": "telegram",
            "platform_user_id": "424242",
            "code": "missing",
        },
    )

    assert response.status_code == 404


def test_post_link_confirm_rejects_attach_only_conflict(
    node_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.platform.im_gateway_management import identity as im_identity
    from fleetent.platform.im_gateway_management.pending_link_store import PendingLinkStore
    from fleetent.platform.node_management import node_desired_state_api, node_store
    from fleetent.platform.tenancy import store as tenancy_store

    tenancy_store.create_tenant(id="tenant-1", name="Tenant 1")
    mapped = im_identity.get_or_create("telegram", "424242", "tenant-1")
    target, _ = user_store.create_user("Bob", email="bob@example.com", tenant_id="tenant-1")
    assert mapped.id != target.id
    store = PendingLinkStore(ttl=datetime.timedelta(minutes=10))
    store.put("link-code", user_id=target.id, tenant_id="tenant-1")
    monkeypatch.setattr(node_desired_state_api, "_pending_links", store)
    node_key, _ = node_store.register_node("node-a")

    response = node_client.post(
        "/nodes/node-a/link-confirm",
        headers={"Authorization": f"Bearer {node_key}"},
        json={
            "platform": "telegram",
            "platform_user_id": "424242",
            "code": "link-code",
        },
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("authorization", "expected_status"),
    [
        (None, 401),
        ("Bearer ma-" + "0" * 64, 401),
    ],
)
def test_post_link_confirm_rejects_missing_or_invalid_node_key(
    node_client: TestClient,
    authorization: str | None,
    expected_status: int,
) -> None:
    from fleetent.platform.node_management import node_store

    node_store.register_node("node-a")
    headers = {} if authorization is None else {"Authorization": authorization}
    response = node_client.post(
        "/nodes/node-a/link-confirm",
        headers=headers,
        json={
            "platform": "telegram",
            "platform_user_id": "424242",
            "code": "missing",
        },
    )

    assert response.status_code == expected_status


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


def test_get_desired_state_seeds_provider_inline_key_for_model_env(
    node_client: TestClient,
) -> None:
    from fleetent import agent_store
    from fleetent.platform.model_provider_management import provider_admin_store
    from fleetent.platform.node_management import node_store, placement_store

    node_key, _ = node_store.register_node("node-a")
    # The provider row carries the inline model key (the shared source of truth) and no
    # per-agent inject slot is created for it.
    provider_admin_store.add_provider(
        "glm-5",
        "https://example.test/v1/",
        "zai.glm-5",
        provider="zai",
        protocol="openai_chat",
        api_key="sk-provider-inline-key",
        api_key_env="FLEETENT_MODEL_GLM_5_API_KEY",
    )
    agent = agent_store.create_agent(
        "enabled",
        "Help users",
        ["shell"],
        model_overrides={"default": [{"provider_id": "glm-5"}]},
    )
    placement_store.pin_agent(agent.id, "node-a")

    response = node_client.get(
        "/nodes/node-a/desired-state",
        headers={"Authorization": f"Bearer {node_key}"},
    )

    assert response.status_code == 200
    delivered = response.json()["agents"][0]
    # Node-managed agents must receive the provider key the same way platform-direct
    # materialize seeds it into .env, even without a dedicated inject slot.
    assert delivered["secrets"]["FLEETENT_MODEL_GLM_5_API_KEY"] == "sk-provider-inline-key"
    # The inline plaintext key must never leak into the non-secret config payload.
    assert "sk-provider-inline-key" not in str(delivered["config"])
