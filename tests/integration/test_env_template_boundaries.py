"""Integration tests for Platform ENV vs Agent ENV template boundaries."""

from pathlib import Path

from fleetent.agent_config import AgentFile
from fleetent.platform.agent_lifecycle import materialize

ROOT = Path(__file__).resolve().parents[2]


def _env_entries(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        entries[key] = value
    return entries


def test_platform_env_template_contains_only_empty_platform_vars():
    entries = _env_entries(ROOT / ".env.example")

    assert "FLEETENT_SECRET_KEY" in entries
    assert entries
    for value in entries.values():
        assert value == ""
    forbidden_agent_envs = {
        "FLEETENT_MODEL_PRIMARY_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "ACME_DOCS_MCP_TOKEN",
    }
    assert forbidden_agent_envs.isdisjoint(entries)
    assert "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN" in entries
    assert "FLEETENT_CONFLUENCE_TOKEN" in entries


def test_agent_env_template_contains_complete_empty_agent_refs_not_platform_vars():
    entries = _env_entries(ROOT / "agents" / "default" / ".env.example")

    assert "FLEETENT_MODEL_PRIMARY_API_KEY" in entries
    assert "SUPPORT_SLACK_BOT" in entries
    assert "ACME_DOCS_MCP_TOKEN" in entries
    assert entries
    for value in entries.values():
        assert value == ""
    forbidden_platform_envs = {
        "FLEETENT_SECRET_KEY",
        "DATABASE_URL",
        "LOG_FORMAT",
        "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
        "FLEETENT_CONFLUENCE_TOKEN",
    }
    assert forbidden_platform_envs.isdisjoint(entries)


def test_materialized_agent_env_contains_required_refs_not_platform_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = AgentFile(
        name="support",
        version=1,
        models={
            "targets": [
                {
                    "id": "primary",
                    "provider": "anthropic",
                    "protocol": "openai_chat",
                    "base_url": "https://api.anthropic.com/v1/",
                    "model": "claude-haiku-4-5-20251001",
                    "api_key_env": "FLEETENT_AGENT_SUPPORT_MODEL",
                }
            ],
            "routes": {"default": [{"target": "primary"}]},
        },
    )

    home = materialize.write_home(agent)
    entries = _env_entries(home / ".env")

    assert entries == {"FLEETENT_AGENT_SUPPORT_MODEL": ""}
    assert "FLEETENT_SECRET_KEY" not in entries
