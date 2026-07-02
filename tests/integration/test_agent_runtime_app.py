"""Standalone agent runtime: boot one agent home, bind IM, optional HTTP — no platform."""

import datetime
from unittest.mock import AsyncMock

import yaml
from fastapi.testclient import TestClient

import fleetent.runtime.loop as loop
import fleetent.user_store as us
from fleetent import agent_config
from fleetent.governance import approval_store
from fleetent.runtime import agent_app
from tests.integration._migration_template import apply_migrations


class _FakeSupervisor:
    def __init__(self):
        self.started: list[str] = []
        self.stopped = False

    async def start(self, agent_name: str) -> None:
        self.started.append(agent_name)

    async def stop_all(self) -> None:
        self.stopped = True


def _write_home(tmp_path, name="support", **fields):
    home = tmp_path / name
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": name,
        "version": 1,
        "system_prompt": "I am support.",
        "models": agent_config.default_models().model_dump(mode="json"),
    }
    doc.update(fields)
    (home / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return home


async def test_boot_publishes_single_agent_index(tmp_path, monkeypatch):
    home = _write_home(tmp_path)
    sup = _FakeSupervisor()
    rt = await agent_app.boot("support", home=home, supervisor=sup, with_infra=False)

    index = agent_config.current()
    assert set(index.agents) == {"support"}
    assert index.default == "support"
    assert rt.agent.name == "support"
    assert rt.agent.system_prompt == "I am support."


async def test_boot_starts_agent_slack_connector(tmp_path):
    home = _write_home(tmp_path)
    sup = _FakeSupervisor()
    await agent_app.boot("support", home=home, supervisor=sup, with_infra=False)
    assert sup.started == ["support"]


async def test_boot_skips_im_when_disabled(tmp_path):
    home = _write_home(tmp_path)
    sup = _FakeSupervisor()
    await agent_app.boot("support", home=home, supervisor=sup, with_infra=False, start_im=False)
    assert sup.started == []


async def test_boot_starts_agent_telegram_connector(tmp_path):
    home = _write_home(tmp_path)
    sup, tg = _FakeSupervisor(), _FakeSupervisor()
    await agent_app.boot(
        "support", home=home, supervisor=sup, telegram_supervisor=tg, with_infra=False
    )
    assert tg.started == ["support"]


async def test_boot_skips_telegram_when_im_disabled(tmp_path):
    home = _write_home(tmp_path)
    sup, tg = _FakeSupervisor(), _FakeSupervisor()
    await agent_app.boot(
        "support",
        home=home,
        supervisor=sup,
        telegram_supervisor=tg,
        with_infra=False,
        start_im=False,
    )
    assert tg.started == []


async def test_runtime_stop_stops_both_supervisors(tmp_path):
    home = _write_home(tmp_path)
    sup, tg = _FakeSupervisor(), _FakeSupervisor()
    rt = await agent_app.boot(
        "support", home=home, supervisor=sup, telegram_supervisor=tg, with_infra=False
    )
    await rt.stop()
    assert sup.stopped and tg.stopped


def test_build_app_serves_chat_ws_health_and_no_admin():
    app = agent_app.build_app("support")
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/chat" in paths
    assert "/ws" in paths
    assert "/health" in paths
    # No platform admin surface on the agent runtime.
    assert not any(p and p.startswith("/admin") for p in paths)


def test_chat_streams_and_applies_agent(tmp_path, monkeypatch):
    # Functional /chat: proves the route is wired (not just present) and applies the
    # home agent's config to run_stream. (Regression guard: an earlier annotation bug
    # made the routes build but fail at request time.)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    user, api_key = us.create_user("ChatUser")
    home = _write_home(tmp_path, allowed_tools=["shell"], allowed_skills=["weather"])
    agent_config.scan_home(home)

    captured = {}

    async def fake_run_stream(message, **kwargs):
        captured["message"] = message
        captured.update(kwargs)
        yield {"type": "done", "content": "streamed-reply"}

    monkeypatch.setattr(loop, "run_stream", fake_run_stream)

    app = agent_app.build_app("support")
    with TestClient(app) as client:
        resp = client.post(
            "/chat",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert resp.status_code == 200
    assert "streamed-reply" in resp.text
    assert captured["agent_name"] == "support"
    assert captured["system_prompt"] == "I am support."
    assert "shell" in captured["allowed_tools"]
    assert captured["allowed_skills"] == ["weather"]


def test_chat_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    app = agent_app.build_app("support")
    with TestClient(app) as client:
        assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_resolve_home_uses_fleetent_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    assert agent_app.resolve_home("support") == (
        tmp_path / "tenants" / "default" / "agents" / "support"
    )
    # explicit override wins
    assert agent_app.resolve_home("support", home=tmp_path / "x") == tmp_path / "x"


# ── per-agent skill index from home/skills (skill-runtime-per-agent-index) ────


async def test_boot_builds_skill_index_from_home_skills(tmp_path, monkeypatch):
    """boot() scans <home>/skills/ so the process skill index reflects this agent."""
    from fleetent.skills import registry as skill_registry

    home = _write_home(tmp_path)
    skill_dir = home / "skills" / "crm-ops"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: CRM operations helper\n---\nbody", encoding="utf-8"
    )
    # Ensure the global env does not point the scanner elsewhere.
    monkeypatch.delenv("FLEETENT_SKILLS_DIR", raising=False)

    sup = _FakeSupervisor()
    await agent_app.boot("support", home=home, supervisor=sup, with_infra=False)

    assert "crm-ops" in skill_registry._index


async def test_boot_safe_when_home_has_no_skills_dir(tmp_path, monkeypatch):
    """No <home>/skills/ → boot succeeds; the home-specific skill is absent."""
    from fleetent.skills import registry as skill_registry

    home = _write_home(tmp_path)
    monkeypatch.delenv("FLEETENT_SKILLS_DIR", raising=False)

    sup = _FakeSupervisor()
    await agent_app.boot("support", home=home, supervisor=sup, with_infra=False)

    assert "crm-ops" not in skill_registry._index


async def test_boot_reconciles_expired_approvals_in_agent_state(tmp_path, monkeypatch):
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.session import manager as session_mgr

    home = _write_home(tmp_path)
    agent_app._redirect_agent_data_paths(home)
    agent_app._init_agent_db_schema(home / "data", agent_name="support", tenant_id="default")
    approval_store.insert_approval(
        id="expired",
        session_id="slack:dm:U_REQ:1.1",
        requester_user_id="U_REQ",
        risk_level="medium",
        tool_name="send_im_message",
        tool_args="{}",
        created_at=(datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=48)).isoformat(),
    )
    monkeypatch.setattr(
        sandbox_enablement,
        "get_effective_mode",
        AsyncMock(return_value=sandbox_enablement.Mode.OFF),
    )
    monkeypatch.setattr(session_mgr, "start_session_maintenance", lambda: None)

    sup = _FakeSupervisor()
    await agent_app.boot("support", home=home, supervisor=sup, with_infra=True, start_im=False)

    assert approval_store.get_approval("expired")["status"] == "timeout"


async def test_start_infra_injects_http_knowledge_provider_from_env_ref(
    tmp_path, monkeypatch
) -> None:
    from fleetent import long_term_ctx
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.session import manager as session_mgr

    home = _write_home(
        tmp_path,
        knowledge={
            "enabled": True,
            "bindings": [{"tenant_id": "default", "kb_id": "kb-1"}],
            "provider": {
                "type": "http",
                "url": "https://kb.example/search",
                "auth_ref": "env:FLEETENT_KB_SERVICE_KEY",
            },
        },
    )
    agent = agent_config.load_agent_home_file(home / "agent.yaml")
    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-env-token")
    monkeypatch.setattr(
        sandbox_enablement,
        "get_effective_mode",
        AsyncMock(return_value=sandbox_enablement.Mode.OFF),
    )
    monkeypatch.setattr(session_mgr, "start_session_maintenance", lambda: None)

    await agent_app._start_infra(agent, home / "data")

    provider = long_term_ctx._knowledge_provider
    assert isinstance(provider, long_term_ctx.HttpKnowledgeProvider)
    assert provider._url == "https://kb.example/search"
    assert provider._service_key == "svc-env-token"


async def test_start_infra_keeps_default_local_knowledge_provider_when_unconfigured(
    tmp_path, monkeypatch
) -> None:
    from fleetent import long_term_ctx
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.session import manager as session_mgr

    home = _write_home(
        tmp_path,
        knowledge={
            "enabled": True,
            "bindings": [{"tenant_id": "default", "kb_id": "kb-1"}],
        },
    )
    agent = agent_config.load_agent_home_file(home / "agent.yaml")
    monkeypatch.setattr(
        sandbox_enablement,
        "get_effective_mode",
        AsyncMock(return_value=sandbox_enablement.Mode.OFF),
    )
    monkeypatch.setattr(session_mgr, "start_session_maintenance", lambda: None)

    await agent_app._start_infra(agent, home / "data")

    assert long_term_ctx._knowledge_provider is None


async def test_start_infra_injects_http_knowledge_provider_from_file_ref(
    tmp_path, monkeypatch
) -> None:
    from fleetent import long_term_ctx
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.session import manager as session_mgr

    secret_path = tmp_path / "secrets" / "kb-token.txt"
    secret_path.parent.mkdir(parents=True)
    secret_path.write_text("svc-file-token", encoding="utf-8")
    home = _write_home(
        tmp_path,
        knowledge={
            "enabled": True,
            "bindings": [{"tenant_id": "default", "kb_id": "kb-1"}],
            "provider": {
                "type": "http",
                "url": "https://kb.example/search",
                "auth_ref": f"file://{secret_path}",
            },
        },
    )
    agent = agent_config.load_agent_home_file(home / "agent.yaml")
    monkeypatch.setattr(
        sandbox_enablement,
        "get_effective_mode",
        AsyncMock(return_value=sandbox_enablement.Mode.OFF),
    )
    monkeypatch.setattr(session_mgr, "start_session_maintenance", lambda: None)

    await agent_app._start_infra(agent, home / "data")

    provider = long_term_ctx._knowledge_provider
    assert isinstance(provider, long_term_ctx.HttpKnowledgeProvider)
    assert provider._service_key == "svc-file-token"


async def test_managed_home_defaults_to_http_knowledge_provider_from_kb_host_config(
    tmp_path, monkeypatch
) -> None:
    from fleetent import long_term_ctx
    from fleetent.integrations.sandbox import enablement as sandbox_enablement
    from fleetent.node.config import NodeConfig
    from fleetent.node.provider import DesiredAgent, DesiredState
    from fleetent.node.reconcile import NodeReconciler
    from fleetent.session import manager as session_mgr

    class _Backend:
        def spawn(self, agent_name: str, tenant_id: str = "default") -> None:
            del agent_name, tenant_id

        def stop(self, agent_name: str, tenant_id: str = "default") -> None:
            del agent_name, tenant_id

        def is_alive(self, agent_name: str, tenant_id: str = "default") -> int | None:
            del agent_name, tenant_id
            return None

        def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
            del agent_name, tenant_id
            return None

    (tmp_path / "kb-service.yaml").write_text(
        yaml.safe_dump(
            {
                "service": {
                    "service_key_ref": "env:FLEETENT_KB_SERVICE_KEY",
                    "host": "127.0.0.1",
                    "port": 9876,
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-managed-kb")
    monkeypatch.setattr(
        sandbox_enablement,
        "get_effective_mode",
        AsyncMock(return_value=sandbox_enablement.Mode.OFF),
    )
    monkeypatch.setattr(session_mgr, "start_session_maintenance", lambda: None)

    reconciler = NodeReconciler(
        NodeConfig(
            platform_url="https://platform.internal",
            node_id="node-a",
            service_key="ma-" + "1" * 64,
            home_dir=tmp_path,
            interval_seconds=10,
        ),
        _Backend(),
    )
    reconciler.reconcile(
        DesiredState(
            node_id="node-a",
            agents=[
                DesiredAgent(
                    agent_id=101,
                    name="support",
                    tenant_id="tenant-1",
                    config={
                        "name": "support",
                        "version": 1,
                        "tenant_id": "tenant-1",
                        "models": {
                            "targets": [
                                {
                                    "id": "default",
                                    "provider": "anthropic",
                                    "protocol": "openai_chat",
                                    "base_url": "https://api.anthropic.test/v1",
                                    "model": "claude-haiku",
                                    "api_key_env": "SUPPORT_MODEL_KEY",
                                }
                            ],
                            "routes": {"default": [{"target": "default"}]},
                        },
                        "knowledge": {
                            "enabled": True,
                            "bindings": [{"tenant_id": "tenant-1", "kb_id": "support-kb"}],
                        },
                    },
                    secrets={},
                )
            ],
        )
    )

    home = tmp_path / "tenants" / "tenant-1" / "agents" / "support"
    agent = agent_config.load_agent_home_file(home / "agent.yaml")

    await agent_app._start_infra(agent, home / "data")

    provider = long_term_ctx._knowledge_provider
    assert isinstance(provider, long_term_ctx.HttpKnowledgeProvider)
    assert provider._url == "http://127.0.0.1:9876/search"
    assert provider._service_key == "svc-managed-kb"
