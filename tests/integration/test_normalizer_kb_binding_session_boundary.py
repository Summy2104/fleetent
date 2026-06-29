from unittest.mock import AsyncMock

import yaml

import fleetent.agent_config as agent_config
from fleetent.im_gateway import access, normalizer
from tests.integration._migration_template import apply_migrations


def _setup_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)


def _write_agent(home, monkeypatch, kb_id: str, *, rescan: bool = True) -> None:
    doc = {
        "name": "default",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
        "knowledge": {
            "enabled": True,
            "bindings": [{"tenant_id": "default", "kb_id": kb_id, "default": True}],
        },
        "im": {
            "supports_dm": True,
            "slack": {
                "bot_token_env": "TEST_BOT_TOKEN",
                "app_token_env": "TEST_APP_TOKEN",
                "access": {"allow_users": ["u1"]},
            },
        },
    }
    d = home / "tenants" / "default" / "agents" / "default"
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    if rescan:
        agent_config.scan_home(d)


def _msg(session_id: str, replies: list[str]):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id=session_id,
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id="C-SS",
        workspace_id="",
    )


async def test_kb_bindings_refresh_only_on_next_session(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _write_agent(tmp_path, monkeypatch, kb_id="kb-old")
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")
    from fleetent.session import manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "data" / "sessions")

    import fleetent.integrations.sandbox.enablement as se
    import fleetent.runtime.loop as agent_loop

    monkeypatch.setattr(se, "get_effective_mode", AsyncMock(return_value=se.Mode.OFF))

    seen: list[str] = []

    async def fake_run(messages, **kwargs):
        del messages, kwargs
        agent = agent_config.active_agent_or_default()
        seen.append(agent.knowledge.bindings[0].kb_id)
        return "done"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies: list[str] = []
    await normalizer.route(_msg("thread:existing", replies))
    _write_agent(tmp_path, monkeypatch, kb_id="kb-new", rescan=False)
    await normalizer.route(_msg("thread:existing", replies))
    await normalizer.route(_msg("thread:new", replies))

    assert seen == ["kb-old", "kb-old", "kb-new"]
