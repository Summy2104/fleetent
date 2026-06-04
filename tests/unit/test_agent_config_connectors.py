"""agent.yaml connectors.slack schema + secret scan + index query (per-agent-slack-connector)."""

import pytest
import yaml

from fleetent import agent_config


def _write(root, name, **fields):
    doc = {"name": name, "version": 1}
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_slack_connector_parsed(tmp_path):
    _write(
        tmp_path,
        "support",
        connectors={
            "slack": {
                "bot_token_env": "SUPPORT_SLACK_BOT",
                "app_token_env": "SUPPORT_SLACK_APP",
                "channels": ["C1"],
            }
        },
    )
    af = agent_config.load_agent_file(tmp_path / "support")
    assert af.connectors.slack is not None
    assert af.connectors.slack.bot_token_env == "SUPPORT_SLACK_BOT"
    assert af.connectors.slack.app_token_env == "SUPPORT_SLACK_APP"
    assert af.connectors.slack.channels == ["C1"]


def test_connectors_optional(tmp_path):
    _write(tmp_path, "bare")
    af = agent_config.load_agent_file(tmp_path / "bare")
    assert af.connectors.slack is None


def test_channels_default_empty(tmp_path):
    _write(
        tmp_path,
        "support",
        connectors={"slack": {"bot_token_env": "B", "app_token_env": "A"}},
    )
    af = agent_config.load_agent_file(tmp_path / "support")
    assert af.connectors.slack.channels == []


def test_inline_token_under_connectors_rejected(tmp_path):
    _write(
        tmp_path,
        "support",
        connectors={
            "slack": {
                "bot_token_env": "xoxb-0123456789-abcdefABCDEF0123456789",
                "app_token_env": "SUPPORT_SLACK_APP",
            }
        },
    )
    with pytest.raises(ValueError) as exc:
        agent_config.load_agent_file(tmp_path / "support")
    assert "support" in str(exc.value)


def test_index_slack_agents(tmp_path):
    _write(
        tmp_path,
        "support",
        connectors={"slack": {"bot_token_env": "B1", "app_token_env": "A1"}},
    )
    _write(
        tmp_path,
        "sales",
        connectors={"slack": {"bot_token_env": "B2", "app_token_env": "A2"}},
    )
    _write(tmp_path, "no-slack")
    index = agent_config.build_index(tmp_path)
    assert set(index.slack_agents()) == {"support", "sales"}
