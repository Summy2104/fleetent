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


async def test_route_threads_owner_to_allowlist(monkeypatch):
    captured = {}

    def fake_is_allowed(owner_id, platform, channel_id, workspace_id=None):
        captured["owner_id"] = owner_id
        return False  # stop before agent loop

    from fleetent.platform.im_gateway_management import im_channel_allowlist

    monkeypatch.setattr(im_channel_allowlist, "is_allowed", fake_is_allowed)
    replies = []
    await normalizer.route(_msg("ownerX", replies))
    assert captured["owner_id"] == "ownerX"


async def test_session_namespaced_by_owner(monkeypatch):
    from fleetent.platform.im_gateway_management import im_channel_allowlist

    monkeypatch.setattr(im_channel_allowlist, "is_allowed", lambda *a, **k: True)
    monkeypatch.setattr(normalizer.im_user_store, "check_allowed_by_user_id", lambda _u: True)

    import contextlib

    from fleetent import agent_loop
    from fleetent.session import manager as session_mgr

    seen: list[str] = []

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        seen.append(sid)
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: None)
    monkeypatch.setattr(agent_loop, "run", lambda **k: _async("ok"))

    await normalizer.route(_msg("ownerA", []))
    await normalizer.route(_msg("ownerB", []))
    assert seen == ["ownerA:s1", "ownerB:s1"]


def _async(value):
    async def _coro():
        return value

    return _coro()
