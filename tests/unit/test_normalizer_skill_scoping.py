"""agent-skill-scoping: the IM gateway narrows the <available_skills> catalog to
the bound agent's allowed_skills (empty/None → no narrowing)."""

from unittest.mock import AsyncMock

import fleetent.agent_store as agent_store
import fleetent.im_user_store as im_user_store
import fleetent.skills as sr
import fleetent.user_store as user_store
from fleetent.im_gateway import normalizer
from fleetent.platform.im_gateway_management import im_channel_allowlist as acl
from fleetent.platform.im_gateway_management import im_connector_store as ics


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


async def _common_patches(monkeypatch, captured):
    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", lambda _uid: True)
    import fleetent.agent_loop as agent_loop
    import fleetent.integrations.sandbox.enablement as se

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
    await _common_patches(monkeypatch, captured)

    agent = agent_store.create_agent("ss-bot", "Sys.", ["shell"], allowed_skills=["weather"])
    agent_store.assign_channel("slack", "C-SS", agent.id)

    replies: list[str] = []
    await normalizer.route(_msg(replies))

    assert captured.get("allowed_skills") == ["weather"]


async def test_route_no_agent_does_not_narrow(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    captured: dict = {}
    await _common_patches(monkeypatch, captured)

    replies: list[str] = []
    await normalizer.route(_msg(replies))

    assert captured.get("allowed_skills") is None
