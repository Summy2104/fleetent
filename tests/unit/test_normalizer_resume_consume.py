"""Normalizer consumes resume_pending: detect on load, log + clear, best-effort."""

import contextlib

from fleetent.im_gateway import normalizer


def _msg(replies, *, session_id="s1"):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        owner_id=None,
        session_id=session_id,
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id="C1",
    )


def _async(value):
    async def _coro():
        return value

    return _coro()


def _wire_common(monkeypatch, tmp_path):
    from fleetent.agent_config import AgentAccess, AgentFile, default_models
    from fleetent.im_gateway import access
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    agent = AgentFile(
        name="a",
        version=1,
        models=default_models(),
        access=AgentAccess(allow_users=["u1"]),
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
    monkeypatch.setattr(agent_loop, "run", lambda **k: _async("ok"))


async def test_resume_pending_detected_clears_flag(monkeypatch, tmp_path):
    from fleetent.platform.chat_management import session_admin_store

    _wire_common(monkeypatch, tmp_path)
    monkeypatch.setattr(session_admin_store, "get_meta", lambda _sid: {"resume_pending": 1})
    cleared: list[str] = []
    monkeypatch.setattr(
        session_admin_store, "clear_resume_pending", lambda sid: cleared.append(sid)
    )

    await normalizer.route(_msg([]))

    assert cleared == ["s1"]


async def test_no_resume_pending_does_not_clear(monkeypatch, tmp_path):
    from fleetent.platform.chat_management import session_admin_store

    _wire_common(monkeypatch, tmp_path)
    monkeypatch.setattr(session_admin_store, "get_meta", lambda _sid: {"resume_pending": 0})
    cleared: list[str] = []
    monkeypatch.setattr(
        session_admin_store, "clear_resume_pending", lambda sid: cleared.append(sid)
    )

    await normalizer.route(_msg([]))

    assert cleared == []


async def test_resume_consume_failure_does_not_block(monkeypatch, tmp_path):
    from fleetent.platform.chat_management import session_admin_store

    _wire_common(monkeypatch, tmp_path)

    def _boom(_sid):
        raise RuntimeError("db down")

    monkeypatch.setattr(session_admin_store, "get_meta", _boom)
    replies: list[str] = []

    # Message must still be processed despite resume-consume failure
    await normalizer.route(_msg(replies))
    # agent_loop.run mocked to "ok"; route completes without raising
