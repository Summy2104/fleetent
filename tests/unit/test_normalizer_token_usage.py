"""Normalizer threads run()'s usage_out into session_mgr.save(token_usage=...)."""

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


def _wire(monkeypatch, tmp_path, run_impl):
    from fleetent.agent_config import AgentAccess, AgentFile, default_models
    from fleetent.im_gateway import access
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    agent = AgentFile(
        name="a", version=1, models=default_models(), access=AgentAccess(allow_users=["u1"])
    )
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: agent)
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))

    saved: dict = {}

    async def fake_save(session_id, history, *a, **k):
        saved["token_usage"] = k.get("token_usage")

    monkeypatch.setattr(session_mgr, "save", fake_save)
    monkeypatch.setattr(agent_loop, "run", run_impl)
    return saved


async def test_usage_out_threaded_to_save(monkeypatch, tmp_path):
    async def run_with_usage(**kwargs):
        # Simulate run filling the caller-provided usage_out sink.
        sink = kwargs.get("usage_out")
        if sink is not None:
            sink.append((100, 50))
        return "ok"

    saved = _wire(monkeypatch, tmp_path, run_with_usage)
    await normalizer.route(_msg([]))
    assert saved["token_usage"] == (100, 50)


async def test_no_usage_results_in_none_token_usage(monkeypatch, tmp_path):
    async def run_no_usage(**kwargs):
        return "ok"  # never touches usage_out

    saved = _wire(monkeypatch, tmp_path, run_no_usage)
    await normalizer.route(_msg([]))
    assert saved["token_usage"] is None
