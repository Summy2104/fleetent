"""Tests for cron task <-> session binding (S3)."""

import fleetent.cron_scheduler as cron
import fleetent.schedule_store as ss
from fleetent.identity import Principal

# ── schedule_store session_id column (S3, re-grafted onto main's db.py regime) ──


def test_create_persists_session_id(isolated_schedule_db):
    ss.create("daily", "0 9 * * *", "UTC", "u1", "report", session_id="cron/daily")
    tasks = ss.list_tasks()
    assert tasks[0]["session_id"] == "cron/daily"


def test_create_session_id_defaults_none(isolated_schedule_db):
    ss.create("oneoff", "0 9 * * *", "UTC", "u1", "do it")
    assert ss.list_tasks()[0]["session_id"] is None


# NOTE: zhangyang's S3 also defined cron jobs (with session_id) via a legacy YAML file.
# main deliberately dropped yaml cron loading in favour of DB-only runtime management
# (cron_scheduler.test_cron_yaml_loader_is_removed enforces this), so the yaml-loader
# test was removed during the merge. Session binding itself is preserved via the DB
# path (schedule_store.create(session_id=) + _fire) — see the tests above/below.


# ── _fire binding semantics ──────────────────────────────────────────────────


async def test_fire_independent_semantics_unique_sessions(tmp_path, monkeypatch):
    import fleetent.session.manager as sm

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(
        cron,
        "_resolve_cron_principal",
        lambda task: Principal(user_id=task["user_id"], tenant_id="default"),
    )
    sids: list[str] = []

    async def fake_run(messages, agent_name=None, principal=None, connectors=None, suppress_outbound=False):
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
    import fleetent.session.manager as sm

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(
        cron,
        "_resolve_cron_principal",
        lambda task: Principal(user_id=task["user_id"], tenant_id="default"),
    )
    captured_msgs: list = []

    async def fake_run(messages, agent_name=None, principal=None, connectors=None, suppress_outbound=False):
        captured_msgs.append(list(messages))  # snapshot what run received (at entry)
        # Simulate agent_loop.run mutating the list in place into the full convo:
        # append a tool-call assistant turn + the final assistant reply.
        n = len(captured_msgs)
        messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": "t"}]})
        messages.append({"role": "assistant", "content": f"reply-{n}"})
        return f"reply-{n}"

    monkeypatch.setattr(cron, "_agent_run", fake_run)
    # action type: runs the agent and accumulates the conversation, but injects no
    # delivery statement (generate-only) — so the run sees the raw turn and fixed-session
    # accumulation is asserted on the unmodified messages.
    task = {
        "id": "t2",
        "message": "tick",
        "user_id": "u1",
        "agent_name": "a1",
        "session_id": "cron/fixed",
        "task_type": "action",
    }
    await cron._fire(task)
    await cron._fire(task)
    # First fire received just the user message.
    assert len(captured_msgs[0]) == 1
    # Second fire received the FULL stored conversation from fire 1 (user + tool turn
    # + final assistant) plus the new user message → 4 messages.
    assert len(captured_msgs[1]) == 4
    assert captured_msgs[1][2] == {"role": "assistant", "content": "reply-1"}
    assert captured_msgs[1][3] == {"role": "user", "content": "tick"}


async def test_fire_saves_with_user_and_agent(tmp_path, monkeypatch):
    import fleetent.session.manager as sm

    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(
        cron,
        "_resolve_cron_principal",
        lambda task: Principal(user_id=task["user_id"], tenant_id="default"),
    )
    captured: dict = {}

    async def fake_run(messages, agent_name=None, principal=None, connectors=None, suppress_outbound=False):
        messages.append({"role": "assistant", "content": "ok"})  # run mutates in place
        return "ok"

    async def spy_save(sid, messages, user_id=None):
        captured.update(sid=sid, user_id=user_id, n=len(messages))

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
    assert captured["user_id"] == "u9"
    assert captured["n"] == 2  # full conversation persisted (user + assistant)
