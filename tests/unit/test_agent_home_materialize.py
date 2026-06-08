"""Platform materializes a runnable agent home (agent.yaml + .env scaffold)."""

import yaml

from fleetent.agent_config import (
    AgentConnectors,
    AgentFile,
    AgentKnowledge,
    AgentKnowledgeBinding,
    AgentRetrievalPolicy,
    ConnectorAccess,
    SlackConnector,
    default_models,
    load_agent_file,
)
from fleetent.intelligence.knowledge_base.config import KnowledgeConfigSnapshot
from fleetent.platform.agent_lifecycle import materialize


def _agent(name="support", **fields):
    base = dict(
        name=name,
        version=1,
        system_prompt="Help the user.",
        allowed_tools=["shell"],
        allowed_skills=["weather"],
        models=default_models(),
        connectors=AgentConnectors(
            slack=SlackConnector(
                bot_token_env="SUP_BOT",
                app_token_env="SUP_APP",
                access=ConnectorAccess(allow_users=["u_alice"]),
            )
        ),
    )
    base.update(fields)
    return AgentFile(**base)


def test_create_writes_runnable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home = materialize.write_home(_agent())

    assert home == tmp_path / "agents" / "support"
    af = load_agent_file(home)  # round-trips through the home schema (dir name == name)
    assert af.system_prompt == "Help the user."
    assert af.allowed_tools == ["shell"]
    assert af.connectors.slack is not None
    assert af.connectors.slack.access.allow_users == ["u_alice"]
    assert af.connectors.slack.bot_token_env == "SUP_BOT"


def test_env_scaffold_has_names_only_no_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home = materialize.write_home(_agent())
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert (home / "data").is_dir()
    assert "FLEETENT_SECRET_KEY=" not in env_text
    assert "DATABASE_URL=" not in env_text
    assert "SUP_BOT=" in env_text
    assert "SUP_APP=" in env_text
    # only names, no secret values seeded
    for line in env_text.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            assert line.split("=", 1)[1] == ""


def test_env_scaffold_includes_model_api_key_envs(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home = materialize.write_home(
        _agent(
            models={
                "targets": [
                    {
                        "id": "primary",
                        "provider": "anthropic",
                        "protocol": "openai_chat",
                        "base_url": "https://api.anthropic.com/v1/",
                        "model": "claude-sonnet",
                        "api_key_env": "FLEETENT_MODEL_PRIMARY_API_KEY",
                    }
                ],
                "routes": {"default": [{"target": "primary"}]},
            }
        )
    )

    env_text = (home / ".env").read_text(encoding="utf-8")

    assert "FLEETENT_MODEL_PRIMARY_API_KEY=" in env_text
    assert "ANTHROPIC_API_KEY=" not in env_text


def test_update_rewrites_yaml_preserves_env_values(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    home = materialize.write_home(_agent())
    # operator fills in a real secret
    (home / ".env").write_text("SUP_BOT=xoxb-real\nSUP_APP=xapp-real\n", encoding="utf-8")

    # edit the definition and re-materialize
    materialize.write_home(_agent(system_prompt="Updated prompt."))

    af = load_agent_file(home)
    assert af.system_prompt == "Updated prompt."  # yaml rewritten
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert "SUP_BOT=xoxb-real" in env_text  # operator value preserved
    assert "SUP_APP=xapp-real" in env_text


def test_default_closed_access_when_not_authored(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = AgentFile(name="bare", version=1, models=default_models())  # no connectors authored
    home = materialize.write_home(agent)
    af = load_agent_file(home)
    # No connectors means no access config; default-closed policy is per-connector.
    assert af.connectors.slack is None
    assert af.connectors.telegram is None


def test_materialize_splits_agent_knowledge_and_kb_service_config(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = _agent(
        knowledge=AgentKnowledge(
            enabled=True,
            bindings=[
                AgentKnowledgeBinding(
                    tenant_id="acme",
                    kb_id="support-kb",
                    default=True,
                )
            ],
            retrieval_policy=AgentRetrievalPolicy(
                mode="hybrid",
                top_k=8,
                rerank=True,
                embedding_route="embedding",
                rerank_route="rerank",
            ),
        )
    )
    knowledge_config = KnowledgeConfigSnapshot.model_validate(
        {
            "knowledge_bases": [
                {
                    "id": "support-kb",
                    "tenant_id": "acme",
                    "sources": [
                        {
                            "id": "support-drive",
                            "type": "google_drive",
                            "folder_id": "folder-1",
                            "access_token_env": "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
                            "refresh_token_env": "FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN",
                            "client_id_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_ID",
                            "client_secret_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET",
                        }
                    ],
                }
            ]
        }
    )

    home = materialize.write_home(agent, knowledge_config=knowledge_config)

    agent_yaml = yaml.safe_load((home / "agent.yaml").read_text(encoding="utf-8"))
    assert "knowledge_base" not in agent_yaml
    assert agent_yaml["knowledge"]["bindings"] == [
        {
            "tenant_id": "acme",
            "kb_id": "support-kb",
            "default": True,
            "permissions": {"search": True},
        }
    ]
    assert not (tmp_path / "config" / "knowledge.yaml").exists()
    assert "google_drive" not in agent_yaml["knowledge"]


def test_materialize_preserves_kb_source_credential_env_values(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    knowledge_config = KnowledgeConfigSnapshot.model_validate(
        {
            "knowledge_bases": [
                {
                    "id": "support-kb",
                    "tenant_id": "acme",
                    "sources": [
                        {
                            "id": "support-confluence",
                            "type": "confluence",
                            "base_url": "https://example.atlassian.net/wiki",
                            "space_key": "SUPPORT",
                            "username_env": "FLEETENT_CONFLUENCE_USERNAME",
                            "api_token_env": "FLEETENT_CONFLUENCE_TOKEN",
                        }
                    ],
                }
            ]
        }
    )
    home = tmp_path / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".env").write_text(
        "FLEETENT_CONFLUENCE_TOKEN=secret-token\nSUP_BOT=xoxb-real\nSUP_APP=xapp-real\n",
        encoding="utf-8",
    )

    materialize.write_home(_agent(), knowledge_config=knowledge_config)

    env_text = (home / ".env").read_text(encoding="utf-8")
    assert "FLEETENT_CONFLUENCE_TOKEN=" not in env_text
    assert "FLEETENT_CONFLUENCE_USERNAME=" not in env_text
    assert "SUP_BOT=xoxb-real" in env_text
