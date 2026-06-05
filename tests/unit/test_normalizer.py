"""Owner-scoped inbound routing in the normalizer."""

from fleetent.im_gateway import normalizer


def _msg(owner_id, replies, *, session_id="s1", channel_id="C1"):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        owner_id=owner_id,
        session_id=session_id,
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id=channel_id,
    )


async def test_session_namespaced_by_owner(monkeypatch, tmp_path):
    import contextlib

    from fleetent.agent_config import AgentAccess, AgentFile
    from fleetent.im_gateway import access
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    # A resolved agent that allows the test user, so the local gate passes.
    agent = AgentFile(name="a", version=1, access=AgentAccess(allow_users=["u1"]))
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

    await normalizer.route(_msg("ownerA", []))
    await normalizer.route(_msg("ownerB", []))
    assert seen == ["ownerA:s1", "ownerB:s1"]


def _async(value):
    async def _coro():
        return value

    return _coro()
