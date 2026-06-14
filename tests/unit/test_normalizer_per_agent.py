"""route() uses the pre-resolved agent for Slack, skipping get_agent_for_context."""

from unittest.mock import AsyncMock

import yaml

import fleetent.runtime.loop as agent_loop
import fleetent.session.manager as session_mgr
import fleetent.skills as sr
from fleetent import agent_config
from fleetent.im_gateway import access, normalizer
from fleetent.integrations.sandbox import enablement as se


def _write(root, name, **fields):
    # Default connector access allows the test user U1 so the local per-agent gate passes.
    doc = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(),
        "connectors": {
            "supports_dm": True,
            "slack": {
                "bot_token_env": "BOT",
                "app_token_env": "APP",
                "access": {"allow_users": ["U1"]},
            },
        },
    }
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _patches(monkeypatch, tmp_path, captured):
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")
    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))
    monkeypatch.setattr(sr, "available_skills_prompt", lambda **k: "")

    async def fake_run(messages, **kwargs):
        captured["system"] = messages[0]["content"]
        return "done"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    calls = []
    real = normalizer.get_agent_for_context
    monkeypatch.setattr(
        normalizer, "get_agent_for_context", lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    )
    captured["gac_calls"] = calls


def _msg(agent_name=""):
    async def reply(_text):
        pass

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id="user:U1",
        user_id="U1",
        text="hi",
        attachments=[],
        reply_func=reply,
        channel_id="C1",
        agent_name=agent_name,
    )


async def test_route_uses_preresolved_agent_for_slack(tmp_path, monkeypatch):
    _write(tmp_path / "agents", "support", system_prompt="S")
    agent_config.scan(tmp_path / "agents")
    captured: dict = {}
    _patches(monkeypatch, tmp_path, captured)

    await normalizer.route(_msg(agent_name="support"))

    assert captured["system"] == "S"  # support agent applied
    assert captured["gac_calls"] == []  # get_agent_for_context NOT consulted


async def test_route_without_preresolved_agent_uses_index(tmp_path, monkeypatch):
    # Telegram-style: no agent_name stamped → falls back to index resolution.
    # Channel/user routing removed; only default-agent fallback matters now.
    _write(tmp_path / "agents", "def", system_prompt="D")
    agent_config.scan(tmp_path / "agents")
    # Force the single agent as default (scan doesn't auto-default in multi-scan mode)
    agent_config._index = agent_config.AgentConfigIndex(
        agents={"def": agent_config._index.get("def")},
        default="def",
    )
    captured: dict = {}
    _patches(monkeypatch, tmp_path, captured)

    await normalizer.route(_msg(agent_name=""))

    assert captured["system"] == "D"
    assert captured["gac_calls"] == [1]  # index lookup used
