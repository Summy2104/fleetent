"""agent.yaml im.slack schema + secret scan + index query (per-agent-slack-connector)."""

import pytest
import yaml

from fleetent import agent_config


def _write(root, name, **fields):
    doc = {"name": name, "version": 1, "models": agent_config.default_models().model_dump()}
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_im_binding_parsed(tmp_path):
    _write(
        tmp_path,
        "support",
        im={
            "slack": {
                "bot_token_env": "SUPPORT_SLACK_BOT",
                "app_token_env": "SUPPORT_SLACK_APP",
                "access": {"allow_groups": ["C1"]},
            }
        },
    )
    af = agent_config.load_agent_file(tmp_path / "support")
    assert af.im.slack is not None
    assert af.im.slack.bot_token_env == "SUPPORT_SLACK_BOT"
    assert af.im.slack.app_token_env == "SUPPORT_SLACK_APP"
    assert af.im.slack.access.allow_groups == ["C1"]


def test_im_optional(tmp_path):
    _write(tmp_path, "bare")
    af = agent_config.load_agent_file(tmp_path / "bare")
    assert af.im.slack is None


def test_im_support_flags_parse_and_default_false(tmp_path):
    _write(
        tmp_path,
        "support",
        im={
            "supports_dm": True,
            "supports_groups": True,
            "slack": {
                "bot_token_env": "SUPPORT_SLACK_BOT",
                "app_token_env": "SUPPORT_SLACK_APP",
            },
        },
    )
    parsed = agent_config.load_agent_file(tmp_path / "support")
    assert parsed.im.supports_dm is True
    assert parsed.im.supports_groups is True

    _write(
        tmp_path,
        "support-defaults",
        im={
            "slack": {
                "bot_token_env": "SUPPORT_SLACK_BOT",
                "app_token_env": "SUPPORT_SLACK_APP",
            }
        },
    )
    defaults = agent_config.load_agent_file(tmp_path / "support-defaults")
    assert defaults.im.supports_dm is False
    assert defaults.im.supports_groups is False


def test_allow_groups_default_empty(tmp_path):
    _write(
        tmp_path,
        "support",
        im={"slack": {"bot_token_env": "B", "app_token_env": "A"}},
    )
    af = agent_config.load_agent_file(tmp_path / "support")
    # No access block → allow_groups defaults to empty (open to all groups).
    assert af.im.slack.access.allow_groups == []


def test_inline_token_under_im_rejected(tmp_path):
    _write(
        tmp_path,
        "support",
        im={
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
        im={"slack": {"bot_token_env": "B1", "app_token_env": "A1"}},
    )
    _write(
        tmp_path,
        "sales",
        im={"slack": {"bot_token_env": "B2", "app_token_env": "A2"}},
    )
    _write(tmp_path, "no-slack")
    index = agent_config.build_index(tmp_path)
    assert set(index.slack_agents()) == {"support", "sales"}
