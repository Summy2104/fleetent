"""agent-skill-scoping: the IM gateway narrows the <available_skills> catalog to
the bound agent's allowed_skills (empty/None → no narrowing)."""

from unittest.mock import AsyncMock

import yaml

import fleetent.agent_config as agent_config
import fleetent.skills as sr
import fleetent.user_store as user_store
from fleetent.im_gateway import access, normalizer
from fleetent.platform.im_gateway_management import im_channel_allowlist as acl
from fleetent.platform.im_gateway_management import im_connector_store as ics


def _write_agent(root, name, **fields):
    doc = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
    }
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    agent_config.scan(root)


def _setup_db(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "users.db"
    # user_store / ics / acl still use the raw DB_PATH+_init_db path; agent_store
    # moved to the unified db runtime (DATABASE_URL + alembic migrations).
    for mod in (user_store, ics, acl):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    ics._init_db()
    acl._init_db()


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
        tmp_path / "agents",
        "ss-bot",
        system_prompt="Sys.",
        allowed_tools=["shell"],
        allowed_skills=["weather"],
        bindings={"channels": ["slack:C-SS"]},
        access={"allow_users": ["u1"]},
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
