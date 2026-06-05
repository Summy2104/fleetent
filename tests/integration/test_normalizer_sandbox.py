"""SB3: the IM gateway passes the effective sandbox mode + agent features + session
id into agent_loop.run so run_code's schema visibility is gated on the IM path too."""

from unittest.mock import AsyncMock

import yaml

import fleetent.agent_config as agent_config
import fleetent.user_store as user_store
from fleetent.im_gateway import access, normalizer
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


def _write_default_agent(root, name, **fields):
    # A default agent allowing u1 so the per-agent gate passes; no features declared so
    # agent_features stays {} and run_code remains gated by the resolved sandbox mode.
    doc = {
        "name": name,
        "version": 1,
        "access": {"allow_users": ["u1"]},
        "bindings": {"default": True},
    }
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    agent_config.scan(root)


async def test_route_passes_sandbox_context_to_run(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")
    _write_default_agent(tmp_path / "agents", "sb3-bot")

    import fleetent.integrations.sandbox.enablement as se
    import fleetent.runtime.loop as agent_loop

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
