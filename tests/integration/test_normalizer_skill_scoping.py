"""agent-skill-scoping: the IM gateway narrows the <available_skills> catalog to
the bound agent's allowed_skills (empty/None → no narrowing)."""

from unittest.mock import AsyncMock

import yaml

import fleetent.agent_config as agent_config
import fleetent.skills as sr
from fleetent.im_gateway import access, normalizer
from tests.integration._migration_template import apply_migrations


def _write_agent(home, monkeypatch, **fields):
    # Deployed single home agent (forced default — bindings were removed); the IM
    # gate lives on the per-platform connector declaration, allowing u1.
    doc = {
        "name": "default",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
        "connectors": {
            "supports_dm": True,
            "slack": {
                "bot_token_env": "TEST_BOT_TOKEN",
                "app_token_env": "TEST_APP_TOKEN",
                "access": {"allow_users": ["u1"]},
            },
        },
    }
    doc.update(fields)
    d = home / "agents" / "default"
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    agent_config.scan()


def _setup_db(tmp_path, monkeypatch):

    db_path = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)


def _msg(replies):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id="thread:ss",
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id="C-SS",
        workspace_id="",
    )


async def _common_patches(monkeypatch, captured, tmp_path):
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")
    import fleetent.integrations.sandbox.enablement as se
    import fleetent.runtime.loop as agent_loop

    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))

    async def fake_run(messages, **kwargs):
        return "done"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    def _spy(*args, **kwargs):
        captured["allowed_skills"] = kwargs.get("allowed_skills")
        return ""

    monkeypatch.setattr(sr, "available_skills_prompt", _spy)


async def test_route_narrows_catalog_to_agent_allowed_skills(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    captured: dict = {}
    await _common_patches(monkeypatch, captured, tmp_path)

    _write_agent(
        tmp_path,
        monkeypatch,
        system_prompt="Sys.",
        allowed_tools=["shell"],
        allowed_skills=["weather"],
    )

    replies: list[str] = []
    await normalizer.route(_msg(replies))

    assert captured.get("allowed_skills") == ["weather"]


async def test_route_no_agent_blocked_default_closed(tmp_path, monkeypatch):
    # per-agent-im-access: no resolved agent → default-closed, blocked before the loop
    # (this replaces the legacy "no agent = allow-all, no narrowing" behavior).
    _setup_db(tmp_path, monkeypatch)
    captured: dict = {}
    await _common_patches(monkeypatch, captured, tmp_path)
    agent_config.scan(tmp_path / "empty-agents")  # no agents resolved

    replies: list[str] = []
    await normalizer.route(_msg(replies))

    assert replies and replies[0] == normalizer._REJECTION_MSG
    assert "allowed_skills" not in captured  # never reached catalog building
