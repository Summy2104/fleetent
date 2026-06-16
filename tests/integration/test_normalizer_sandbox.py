"""SB3: the IM gateway passes the effective sandbox mode + agent features + session
id into agent_loop.run so run_code's schema visibility is gated on the IM path too."""

from unittest.mock import AsyncMock

import yaml

import fleetent.agent_config as agent_config
from fleetent.im_gateway import access, normalizer
from tests.integration._migration_template import apply_migrations


def _setup_db(tmp_path, monkeypatch):

    db_path = tmp_path / "users.db"
    # normalizer routing queries agent_store, which runs on the unified db runtime.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)


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


def _write_default_agent(home, monkeypatch, **fields):
    # Deployed single home agent allowing u1 (forced default — bindings were removed;
    # the IM gate lives on the connector declaration); no features declared so
    # agent_features stays {} and run_code remains gated by the resolved sandbox mode.
    doc = {
        "name": "default",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
        "im": {
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


async def test_route_passes_sandbox_context_to_run(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")
    _write_default_agent(tmp_path, monkeypatch)

    import fleetent.integrations.sandbox.enablement as se
    import fleetent.runtime.loop as agent_loop

    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.ON))

    captured: dict = {}

    async def fake_run(messages, **kwargs):
        captured.update(kwargs)
        return "done"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies: list[str] = []
    await normalizer.route(_msg(replies))

    assert captured.get("sandbox_mode") is se.Mode.ON
    assert captured.get("session_id") == "thread:sb3"
    # No bound agent here → features default to None/{} and run_code stays gated by mode.
    assert captured.get("agent_features") in (None, {})
