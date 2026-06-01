"""Tests for cron task <-> session binding (S3)."""

from pathlib import Path

import fleetent.cron_scheduler as cron
import fleetent.schedule_store as ss


# ── schedule_store session_id column (D4) ────────────────────────────────────


def test_create_persists_session_id(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "users.db")
    ss.create("daily", "0 9 * * *", "UTC", "u1", None, "report", session_id="cron/daily")
    tasks = ss.list_tasks()
    assert tasks[0]["session_id"] == "cron/daily"


def test_create_session_id_defaults_none(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "users.db")
    ss.create("oneoff", "0 9 * * *", "UTC", "u1", None, "do it")
    assert ss.list_tasks()[0]["session_id"] is None


# ── load_cron_yaml session_id (D1) ───────────────────────────────────────────


def test_load_cron_yaml_session_id(tmp_path):
    p = tmp_path / "cron.yaml"
    p.write_text(
        "jobs:\n"
        "  - id: j1\n    name: J1\n    cron: '0 9 * * *'\n    user_id: u1\n"
        "    message: hi\n    session_id: cron/fixed\n"
        "  - id: j2\n    name: J2\n    cron: '0 9 * * *'\n    user_id: u1\n    message: yo\n"
    )
    jobs = {j["id"]: j for j in cron.load_cron_yaml(p)}
    assert jobs["j1"]["session_id"] == "cron/fixed"
    assert jobs["j2"]["session_id"] is None


# ── _fire binding semantics (D1/D2/D3) ───────────────────────────────────────


async def test_fire_independent_semantics_unique_sessions(tmp_path, monkeypatch):
    import fleetent.session_mgr as sm

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path / "sessions")
    sids: list[str] = []

    async def fake_run(messages, user_id, agent_name=None):
        return "ok"

    async def spy_save(sid, messages, **kw):
        sids.append(sid)  # capture the derived session id each fire (no real write)

    monkeypatch.setattr(cron, "_agent_run", fake_run)
    monkeypatch.setattr(sm, "save", spy_save)
    task = {"id": "t1", "message": "go", "user_id": "u1", "agent_name": None, "session_id": None}
    await cron._fire(task)
    await cron._fire(task)
    assert len(set(sids)) == 2  # two distinct derived sessions
    assert all(s.startswith("cron/t1/") for s in sids)


async def test_fire_fixed_semantics_accumulates(tmp_path, monkeypatch):
    import fleetent.session_mgr as sm

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path / "sessions")
    captured_msgs: list = []

    async def fake_run(messages, user_id, agent_name=None):
        captured_msgs.append(list(messages))  # snapshot what run received
        return f"reply-{len(captured_msgs)}"

    monkeypatch.setattr(cron, "_agent_run", fake_run)
    task = {
        "id": "t2",
        "message": "tick",
        "user_id": "u1",
        "agent_name": "a1",
        "session_id": "cron/fixed",
    }
    await cron._fire(task)
    await cron._fire(task)
    # 2nd run received the 1st run's accumulated history (user + assistant reply).
    assert len(captured_msgs[0]) == 1  # first fire: just the user message
    assert len(captured_msgs[1]) == 3  # second fire: prev user + prev assistant + new user
    assert captured_msgs[1][1] == {"role": "assistant", "content": "reply-1"}


async def test_fire_saves_with_user_and_agent(tmp_path, monkeypatch):
    import fleetent.session_mgr as sm

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path / "sessions")
    captured: dict = {}

    async def fake_run(messages, user_id, agent_name=None):
        return "ok"

    async def spy_save(sid, messages, user_id=None, agent_name=None):
        captured.update(sid=sid, user_id=user_id, agent_name=agent_name, n=len(messages))

    monkeypatch.setattr(cron, "_agent_run", fake_run)
    monkeypatch.setattr(sm, "save", spy_save)
    task = {
        "id": "t3",
        "message": "hi",
        "user_id": "u9",
        "agent_name": "a9",
        "session_id": "cron/s3",
    }
    await cron._fire(task)
    assert captured["sid"] == "cron/s3"
    assert captured["user_id"] == "u9" and captured["agent_name"] == "a9"
    assert captured["n"] == 2  # user + assistant reply persisted
