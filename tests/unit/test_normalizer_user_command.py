"""IM path: /user command interception + user.md injection in normalizer.route.

Drives route() with a mocked session/loop (no DB), mirroring test_normalizer.py.
"""

from __future__ import annotations

import contextlib

from fleetent.agent_config import (
    AgentFile,
    ImAccess,
    ImBinding,
    SlackBinding,
    default_models,
)
from fleetent.im_gateway import access, normalizer
from fleetent.runtime import loop as agent_loop
from fleetent.runtime import user_instructions as ui
from fleetent.session import manager as session_mgr


def _agent(system_prompt: str = "") -> AgentFile:
    return AgentFile(
        name="a",
        version=1,
        system_prompt=system_prompt,
        models=default_models(),
        im=ImBinding(
            supports_dm=True,
            slack=SlackBinding(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ImAccess(allow_users=["u1"]),
            ),
        ),
    )


def _msg(text: str, replies: list[str]):
    async def reply_func(t):
        replies.append(t)

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id="s1",
        user_id="u1",
        text=text,
        attachments=[],
        reply_func=reply_func,
        channel_id="C1",
    )


def _async(value):
    async def _coro():
        return value

    return _coro()


def _wire_common(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: _agent("BASE"))
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "load_meta", lambda _sid: _async({}))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))


async def test_user_command_intercepted_not_run(monkeypatch, tmp_path) -> None:
    _wire_common(monkeypatch, tmp_path)
    ran: list = []
    monkeypatch.setattr(agent_loop, "run", lambda **k: (ran.append(k), _async("ok"))[1])

    replies: list[str] = []
    await normalizer.route(_msg("/user 永远用中文回答", replies))

    # Reply is the receipt; the loop never ran; the directive landed on disk.
    assert replies and "已追加" in replies[0]
    assert ran == []
    assert "永远用中文回答" in ui.load("a")


async def test_user_view_when_empty(monkeypatch, tmp_path) -> None:
    _wire_common(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_loop, "run", lambda **k: _async("ok"))

    replies: list[str] = []
    await normalizer.route(_msg("/user", replies))
    assert replies and "尚未设置" in replies[0]


async def test_normal_message_injects_user_md(monkeypatch, tmp_path) -> None:
    _wire_common(monkeypatch, tmp_path)
    # Seed a directive for agent "a".
    ui.append("a", "永远用中文回答")

    captured: list[dict] = []

    async def capture_run(**kwargs):
        captured.append(kwargs)
        return "ok"

    monkeypatch.setattr(agent_loop, "run", capture_run)

    await normalizer.route(_msg("你好", []))

    assert captured, "loop.run should have been called for a normal message"
    sys_msg = captured[0]["messages"][0]
    assert sys_msg["role"] == "system"
    content = sys_msg["content"]
    assert "永远用中文回答" in content
    assert content.index("BASE") < content.index("永远用中文回答")
