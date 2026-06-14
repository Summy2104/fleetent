"""Owner-scoped inbound routing in the normalizer."""

from fleetent.im_gateway import normalizer


def _msg(replies, *, session_id="s1", channel_id="C1"):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id=session_id,
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id=channel_id,
    )


async def test_session_id_not_owner_prefixed(monkeypatch, tmp_path):
    import contextlib
    from dataclasses import fields

    from fleetent.agent_config import (
        AgentConnectors,
        AgentFile,
        ConnectorAccess,
        SlackConnector,
        default_models,
    )
    from fleetent.im_gateway import access
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    # A resolved agent that allows the test user via connector access, so the gate passes.
    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            supports_dm=True,
            slack=SlackConnector(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ConnectorAccess(allow_users=["u1"]),
            ),
        ),
    )
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: agent)
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")

    seen: list[str] = []

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        seen.append(sid)
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))
    monkeypatch.setattr(agent_loop, "run", lambda **k: _async("ok"))

    await normalizer.route(_msg([]))
    await normalizer.route(_msg([]))
    # No owner prefix: session id is the adapter-derived id as-is.
    assert seen == ["s1", "s1"]
    # owner_id is removed from the message contract entirely.
    assert "owner_id" not in {f.name for f in fields(normalizer.NormalizedMessage)}


def _async(value):
    async def _coro():
        return value

    return _coro()


async def test_normalizer_propagates_permission_gate_config(monkeypatch, tmp_path):
    """normalizer.route() passes agent's permission_gate_enabled + timeouts to loop.run()."""
    import contextlib

    from fleetent.agent_config import (
        AgentConnectors,
        AgentFile,
        ConnectorAccess,
        SlackConnector,
        default_models,
    )
    from fleetent.im_gateway import access
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    agent = AgentFile(
        name="b",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            supports_dm=True,
            slack=SlackConnector(
                bot_token_env="SLACK_BOT",
                app_token_env="SLACK_APP",
                access=ConnectorAccess(allow_users=["u1"]),
            ),
        ),
        permission_gate_enabled=False,
        permission_gate_medium_timeout_seconds=60,
        permission_gate_high_timeout_seconds=120,
    )
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: agent)
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))

    captured: list[dict] = []

    async def capture_run(**kwargs):
        captured.append(kwargs)
        return "ok"

    monkeypatch.setattr(agent_loop, "run", capture_run)

    await normalizer.route(_msg([]))

    assert captured, "loop.run should have been called"
    assert captured[0].get("permission_gate_enabled") is False
    assert captured[0].get("permission_gate_medium_timeout") == 60
    assert captured[0].get("permission_gate_high_timeout") == 120
