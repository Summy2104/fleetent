"""im-run-failure-fallback (P0): IM 路由在 agent_loop.run 失败时兜底回帖、不冒泡、存会话。"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock

import httpx


def _agent():
    from fleetent.agent_config import (
        AgentFile,
        ImAccess,
        ImBinding,
        SlackBinding,
        default_models,
    )

    return AgentFile(
        name="a",
        version=1,
        models=default_models(),
        im=ImBinding(
            supports_dm=True,
            supports_groups=True,
            slack=SlackBinding(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ImAccess(allow_all_users=True, allow_groups=["C9"]),
            ),
        ),
    )


def _async(value):
    async def _coro():
        return value

    return _coro()


async def _run_route(monkeypatch, *, run_exc):
    """驱动 normalizer.route 一次；run_exc 非空则 agent_loop.run 抛该异常，否则正常返回。
    返回 (replies, save_mock, logger_mock, raised)。"""
    from fleetent.im_gateway import access, normalizer
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: _agent())
    monkeypatch.setattr(access, "APPROVALS_PATH", MagicMock())
    monkeypatch.setattr(normalizer, "_current_date_tz", lambda: ("2026-06-30 (Tuesday)", "UTC"))

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    save_mock = AsyncMock()
    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", save_mock)
    monkeypatch.setattr(session_mgr, "is_resume_pending", lambda _sid: False, raising=False)
    monkeypatch.setattr(
        "fleetent.im_gateway.normalizer.resolve_identity", lambda p, uid: uid, raising=False
    )
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity", lambda p, uid: uid, raising=False
    )

    logger_mock = MagicMock()
    monkeypatch.setattr(normalizer, "logger", logger_mock)

    async def fake_run(**kwargs):
        if run_exc is not None:
            raise run_exc
        return "正常回复"

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies: list[str] = []

    async def _reply(text, blocks=None):
        replies.append(text)

    msg = normalizer.NormalizedMessage(
        platform="slack",
        session_id="slack:thread:C9:300.3",
        user_id="U123",
        text="原始问题",
        attachments=[],
        reply_func=_reply,
        channel_id="C9",
    )
    raised = None
    try:
        await normalizer.route(msg)
    except Exception as exc:  # noqa: BLE001 — 我们要断言"是否冒泡"
        raised = exc
    return replies, save_mock, logger_mock, raised


async def test_run_failure_replies_fallback_and_does_not_raise(monkeypatch):
    replies, _save, _log, raised = await _run_route(
        monkeypatch, run_exc=httpx.ReadTimeout("read timed out")
    )
    assert raised is None, "异常不得冒泡到 IM 适配器"
    assert len(replies) == 1
    assert replies[0].strip(), "兜底提示须非空"


async def test_run_failure_logs_error(monkeypatch):
    _replies, _save, logger_mock, _raised = await _run_route(
        monkeypatch, run_exc=RuntimeError("boom")
    )
    assert logger_mock.error.called, "失败须记 error 日志（不吞异常）"


async def test_run_failure_saves_session(monkeypatch):
    _replies, save_mock, _log, _raised = await _run_route(
        monkeypatch, run_exc=httpx.ReadTimeout("x")
    )
    assert save_mock.await_count >= 1, "失败轮仍须保存会话（用户输入不丢）"


async def test_success_does_not_trigger_fallback(monkeypatch):
    replies, _save, _log, raised = await _run_route(monkeypatch, run_exc=None)
    assert raised is None
    # 正常成功：只投递正常回复，不出现兜底提示
    assert replies == ["正常回复"]
