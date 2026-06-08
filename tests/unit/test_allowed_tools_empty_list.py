"""Tests for allowed_tools empty list semantics in im_gateway/normalizer.py.

Empty list in agent.yaml should behave like None (all tools allowed),
not like an empty allowlist that blocks everything.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import yaml

import fleetent.runtime.loop as agent_loop
import fleetent.session.manager as session_mgr
import fleetent.skills as sr
from fleetent import agent_config
from fleetent.im_gateway import access, normalizer
from fleetent.integrations.sandbox import enablement as se

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_agent(agents_dir, name, allowed_tools):
    doc = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(),
        "connectors": {
            "slack": {
                "bot_token_env": "BOT",
                "app_token_env": "APP",
                "access": {"allow_users": ["U1"]},
            }
        },
        "allowed_tools": allowed_tools,
    }
    d = agents_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _msg(agent_name="bot"):
    async def reply(_text):
        pass

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id="user:U1",
        user_id="U1",
        text="hello",
        attachments=[],
        reply_func=reply,
        channel_id="C1",
        agent_name=agent_name,
    )


def _common_patches(monkeypatch, tmp_path, captured):
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")
    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))
    monkeypatch.setattr(sr, "available_skills_prompt", lambda **k: "")

    async def fake_run(messages, **kwargs):
        captured["allowed_tools"] = kwargs.get("allowed_tools", "NOT_SET")
        return "ok"

    monkeypatch.setattr(agent_loop, "run", fake_run)


# ---------------------------------------------------------------------------
# normalizer.py tests
# ---------------------------------------------------------------------------


async def test_normalizer_empty_allowed_tools_passes_none(monkeypatch, tmp_path):
    """allowed_tools: [] in agent.yaml → normalizer passes None to run(), not []."""
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "bot", allowed_tools=[])
    agent_config.scan(agents_dir)
    captured: dict = {}
    _common_patches(monkeypatch, tmp_path, captured)

    await normalizer.route(_msg(agent_name="bot"))

    assert captured["allowed_tools"] is None, (
        f"Expected None but got {captured['allowed_tools']!r}; "
        "empty allowed_tools should allow all tools, not block all"
    )


async def test_normalizer_nonempty_allowed_tools_passes_list(monkeypatch, tmp_path):
    """allowed_tools: ['run_code'] in agent.yaml → normalizer passes list unchanged."""
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "bot", allowed_tools=["run_code"])
    agent_config.scan(agents_dir)
    captured: dict = {}
    _common_patches(monkeypatch, tmp_path, captured)

    await normalizer.route(_msg(agent_name="bot"))

    assert captured["allowed_tools"] == ["run_code"]
