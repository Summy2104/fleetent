"""SB3: the IM gateway passes the effective sandbox mode + agent features + session
id into agent_loop.run so run_code's schema visibility is gated on the IM path too."""

from unittest.mock import AsyncMock

import fleetent.im_user_store as im_user_store
import fleetent.user_store as user_store
from fleetent.im_gateway import normalizer
from fleetent.platform.im_gateway_management import im_channel_allowlist as acl
from fleetent.platform.im_gateway_management import im_connector_store as ics


def _setup_db(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "users.db"
    for mod in (user_store, ics, acl):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    # normalizer routing queries agent_store, which runs on the unified db runtime.
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
        session_id="thread:sb3",
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id="",
        workspace_id="",
    )


async def test_route_passes_sandbox_context_to_run(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", lambda _uid: True)

    import fleetent.agent_loop as agent_loop
    import fleetent.sandbox_enablement as se

    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.SELECTIVE))

    captured: dict = {}

    async def fake_run(messages, **kwargs):
        captured.update(kwargs)
        return "done"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies: list[str] = []
    await normalizer.route(_msg(replies))

    assert captured.get("sandbox_mode") is se.Mode.SELECTIVE
    assert captured.get("session_id") == "thread:sb3"
    # No bound agent here → features default to None/{} and run_code stays gated by mode.
    assert captured.get("agent_features") in (None, {})
