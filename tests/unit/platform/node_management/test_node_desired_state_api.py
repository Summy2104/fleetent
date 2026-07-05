from __future__ import annotations

from types import SimpleNamespace

from fleetent import agent_store
from fleetent.agent_config import AgentFile, AgentKnowledge, AgentKnowledgeBinding, default_models
from fleetent.config import KBServeSettings
from fleetent.platform.knowledge_base_management.auth import KB_SERVICE_KEY_ENV
from fleetent.platform.node_management import node_desired_state_api


def _agent() -> agent_store.Agent:
    return agent_store.Agent(id=1, name="support", system_prompt="Help", allowed_tools=["shell"])


def _agent_file() -> AgentFile:
    return AgentFile(
        name="support",
        version=1,
        models=default_models(),
        knowledge=AgentKnowledge(
            enabled=True,
            bindings=[AgentKnowledgeBinding(tenant_id="default", kb_id="support-kb", default=True)],
            provider={
                "type": "http",
                "url": "http://kb-serve.test/search",
                "auth_ref": f"env:{KB_SERVICE_KEY_ENV}",
            },
        ),
    )


def test_agent_secrets_backfills_kb_service_key_from_platform_settings(monkeypatch) -> None:
    monkeypatch.setattr(node_desired_state_api.credential_slots, "list_slots", lambda agent: [])
    monkeypatch.setattr(
        node_desired_state_api.secret_store,
        "get_decrypted_bulk",
        lambda agent_id, env_names: {},
    )
    monkeypatch.setattr(
        node_desired_state_api.provider_admin_store,
        "provider_key_for_env",
        lambda env_name: None,
    )
    monkeypatch.setattr(
        node_desired_state_api,
        "Settings",
        lambda: SimpleNamespace(
            kb_serve=KBServeSettings(
                url="http://kb-serve.test",
                service_key_ref="env:FLEETENT_PLATFORM_KB_SERVICE_KEY",
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        node_desired_state_api,
        "resolve_service_key_ref",
        lambda auth_ref: "svc-platform",
        raising=False,
    )

    secrets = node_desired_state_api._agent_secrets(_agent(), _agent_file())

    assert secrets[KB_SERVICE_KEY_ENV] == "svc-platform"


def test_agent_secrets_prefers_per_agent_secret_over_platform_backfill(monkeypatch) -> None:
    monkeypatch.setattr(
        node_desired_state_api.credential_slots,
        "list_slots",
        lambda agent: [SimpleNamespace(env_name=KB_SERVICE_KEY_ENV, mode="inject")],
    )
    monkeypatch.setattr(
        node_desired_state_api.secret_store,
        "get_decrypted_bulk",
        lambda agent_id, env_names: {KB_SERVICE_KEY_ENV: "svc-agent"},
    )
    monkeypatch.setattr(
        node_desired_state_api.provider_admin_store,
        "provider_key_for_env",
        lambda env_name: None,
    )
    monkeypatch.setattr(
        node_desired_state_api,
        "resolve_service_key_ref",
        lambda auth_ref: "svc-platform",
        raising=False,
    )

    secrets = node_desired_state_api._agent_secrets(_agent(), _agent_file())

    assert secrets[KB_SERVICE_KEY_ENV] == "svc-agent"


def test_agent_secrets_skips_kb_backfill_without_kb_serve_config(monkeypatch) -> None:
    monkeypatch.setattr(node_desired_state_api.credential_slots, "list_slots", lambda agent: [])
    monkeypatch.setattr(
        node_desired_state_api.secret_store,
        "get_decrypted_bulk",
        lambda agent_id, env_names: {},
    )
    monkeypatch.setattr(
        node_desired_state_api.provider_admin_store,
        "provider_key_for_env",
        lambda env_name: None,
    )
    monkeypatch.setattr(
        node_desired_state_api,
        "Settings",
        lambda: SimpleNamespace(kb_serve=KBServeSettings()),
        raising=False,
    )

    secrets = node_desired_state_api._agent_secrets(_agent(), _agent_file())

    assert KB_SERVICE_KEY_ENV not in secrets


def test_agent_secrets_warns_and_skips_when_platform_ref_resolution_fails(monkeypatch) -> None:
    warnings: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(node_desired_state_api.credential_slots, "list_slots", lambda agent: [])
    monkeypatch.setattr(
        node_desired_state_api.secret_store,
        "get_decrypted_bulk",
        lambda agent_id, env_names: {},
    )
    monkeypatch.setattr(
        node_desired_state_api.provider_admin_store,
        "provider_key_for_env",
        lambda env_name: None,
    )
    monkeypatch.setattr(
        node_desired_state_api,
        "Settings",
        lambda: SimpleNamespace(
            kb_serve=KBServeSettings(
                url="http://kb-serve.test",
                service_key_ref="env:FLEETENT_PLATFORM_KB_SERVICE_KEY",
            )
        ),
        raising=False,
    )

    def _boom(auth_ref: str) -> str:
        raise ValueError("missing platform kb key")

    monkeypatch.setattr(node_desired_state_api, "resolve_service_key_ref", _boom, raising=False)
    monkeypatch.setattr(
        node_desired_state_api,
        "_logger",
        SimpleNamespace(warning=lambda event, **fields: warnings.append((event, fields))),
    )

    secrets = node_desired_state_api._agent_secrets(_agent(), _agent_file())

    assert KB_SERVICE_KEY_ENV not in secrets
    assert len(warnings) == 1
    event, fields = warnings[0]
    assert event == "desired_state_kb_service_key_backfill_failed"
    assert fields["extra"]["agent"] == "support"
    assert fields["extra"]["env_name"] == KB_SERVICE_KEY_ENV
    assert str(fields["extra"]["exception"]) == "missing platform kb key"
