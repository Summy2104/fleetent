"""Tests for stats_admin_api (/admin/stats, read-only). Covers scenarios 74-85."""

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.observability.traces as trace_store
import fleetent.platform.agent_statistics.stats_admin_api as api
import fleetent.platform.model_provider_management.provider_admin_store as provider_admin_store
import fleetent.user_store as user_store
from fleetent.db import SQLiteDatabase, create_database
from fleetent.observability import TraceEvent
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration._migration_template import apply_migrations


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("db")
    managed_db = tmp_path / "managed.db"
    mp.setenv("ANTHROPIC_API_KEY", "test-key")
    # schedule_store (report scheduling) runs on the unified runtime; point it at a
    # migrated managed DB so scheduled_tasks exists.
    mp.setenv("DATABASE_URL", f"sqlite:///{managed_db}")
    apply_migrations(managed_db)
    # Patch user_store._db directly so _session_for() calls in test bodies work
    # regardless of the autouse _isolate_database_url fixture deleting DATABASE_URL.
    db_instance = create_database(f"sqlite:///{managed_db}")
    mp.setattr(user_store, "_db", lambda: db_instance)
    mp.setattr(api, "fetch_traces", lambda **kw: [])
    mp.setattr(api, "fetch_approvals", lambda agent_id=None: [])
    mp.setattr(api, "agent_allowed_tools", lambda aid: [])
    mp.setattr(api, "pricing_table", lambda: None)
    app = FastAPI()
    app.include_router(api.router)
    yield TestClient(app, raise_server_exceptions=True)
    mp.undo()


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


@pytest.fixture
def real_client(tmp_path, monkeypatch):
    importlib.reload(api)
    managed_db = tmp_path / "managed.db"
    apply_migrations(managed_db)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{managed_db}")
    db_instance = create_database(f"sqlite:///{managed_db}")
    monkeypatch.setattr(user_store, "_db", lambda: db_instance)
    state_db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(state_db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(trace_store, "_state_db", state_db)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def test_no_auth_401(client):
    assert client.get("/admin/stats/agents/ops/overview").status_code == 401


def test_overview_core_metrics(client, monkeypatch):  # 场景 74
    monkeypatch.setattr(
        api,
        "fetch_traces",
        lambda **kw: [
            {
                "user_id": "u1",
                "session_id": "s1",
                "total_tokens": 10,
                "elapsed_s": 1.0,
                "rounds": 2,
            },
            {
                "user_id": "u2",
                "session_id": "s2",
                "total_tokens": 20,
                "elapsed_s": 3.0,
                "rounds": 4,
            },
        ],
    )
    token, _ = _session_for("viewer")
    r = client.get("/admin/stats/agents/ops/overview", headers=_hdr(token))
    assert r.json()["usage"]["calls"] == 2
    assert r.json()["usage"]["total_tokens"] == 30
    assert r.json()["performance"]["latency_p50"] >= 1.0


def test_compare_multi_agent(client, monkeypatch):  # 场景 75
    monkeypatch.setattr(
        api,
        "fetch_traces",
        lambda **kw: [{"total_tokens": 1}] * (3 if kw.get("agent_id") == "a" else 1),
    )
    token, _ = _session_for("admin")
    r = client.get("/admin/stats/compare?agents=a,b&key=calls", headers=_hdr(token))
    assert [row["agent_id"] for row in r.json()] == ["a", "b"]


def test_per_user_ranking_and_masking(client, monkeypatch):  # 场景 76
    monkeypatch.setattr(
        api,
        "fetch_traces",
        lambda **kw: [
            {"user_id": "alice", "total_tokens": 100, "ts": "2026-06-01T00:00:00"},
        ],
    )
    # viewer sees masked user_id
    vtoken, _ = _session_for("viewer")
    rv = client.get("/admin/stats/per-user", headers=_hdr(vtoken))
    assert rv.json()[0]["user_id"] == "***"
    assert rv.json()[0]["total_tokens"] == 100
    # admin sees real
    atoken, _ = _session_for("admin")
    ra = client.get("/admin/stats/per-user", headers=_hdr(atoken))
    assert ra.json()[0]["user_id"] == "alice"


def test_allowed_tools_coverage(client, monkeypatch):  # 场景 78
    monkeypatch.setattr(
        api, "fetch_traces", lambda **kw: [{"messages": [{"tool_calls": [{"name": "read_file"}]}]}]
    )
    monkeypatch.setattr(api, "agent_allowed_tools", lambda aid: ["read_*", "danger_tool"])
    token, _ = _session_for("admin")
    r = client.get("/admin/stats/agents/ops/tools", headers=_hdr(token))
    assert "danger_tool" in r.json()["coverage"]["unused_patterns"]


def test_cost_unconfigured_pending(client, monkeypatch):  # 场景 79 (⏳ placeholder)
    monkeypatch.setattr(api, "fetch_traces", lambda **kw: [{"model_used": "x"}])
    monkeypatch.setattr(api, "pricing_table", lambda: None)
    token, _ = _session_for("admin")
    r = client.get("/admin/stats/agents/ops/overview", headers=_hdr(token))
    assert r.json()["cost"]["status"] == "待数据接入"


def test_approval_stats_visible(client, monkeypatch):  # 场景 80
    monkeypatch.setattr(
        api,
        "fetch_approvals",
        lambda agent_id=None: [{"decision": "approved"}, {"decision": "rejected"}],
    )
    token, _ = _session_for("admin")
    r = client.get("/admin/stats/agents/ops/overview", headers=_hdr(token))
    assert r.json()["approvals"]["triggered"] == 2
    assert r.json()["approvals"]["pass_rate"] == 0.5


def test_user_request_list(client, monkeypatch):  # 场景 82
    monkeypatch.setattr(
        api,
        "fetch_traces",
        lambda **kw: [
            {"user_id": "u1", "request_id": "r1", "ts": "2026-06-01T00:00:00"},
        ],
    )
    token, _ = _session_for("admin")
    r = client.get("/admin/stats/users/u1/requests", headers=_hdr(token))
    assert r.json()[0]["request_id"] == "r1"


def test_request_event_stream_with_subagent(client, monkeypatch):  # 场景 83/84
    monkeypatch.setattr(
        api,
        "fetch_traces",
        lambda **kw: [
            {"request_id": "r1", "session_id": "parent", "ts": "2026-06-01T00:00:00"},
            {"parent_session_id": "parent", "ts": "2026-06-01T00:00:01", "kind": "child"},
        ],
    )
    token, _ = _session_for("admin")
    r = client.get("/admin/stats/requests/r1", headers=_hdr(token))
    assert r.json()["complete"] is True
    assert r.json()["events"][0]["sub_agent_chain"][0]["kind"] == "child"


def test_degraded_trace_without_request_id(client, monkeypatch):  # 场景 85
    monkeypatch.setattr(
        api,
        "fetch_traces",
        lambda **kw: [
            {"session_id": "sess", "user_id": "u1", "ts": "2026-06-01T00:00:00"},
        ],
    )
    token, _ = _session_for("admin")
    r = client.get("/admin/stats/sessions/sess/trace?user_id=u1", headers=_hdr(token))
    assert r.json()["complete"] is False
    assert "request_id" in r.json()["note"]


def test_export_audited(client):  # 场景 81
    token, _ = _session_for("admin")
    assert client.post("/admin/stats/export", headers=_hdr(token)).status_code == 200
    actions = {a["action"] for a in audit.search_audit()}
    assert "stats_export" in actions


def test_scheduled_report_endpoint_removed(client):
    """agent-owned-scheduled-tasks: the stats-report stub (which only registered a
    scheduled task + audit, never sent an email) was removed; scheduling is agent-owned."""
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/stats/reports",
        headers=_hdr(token),
        json={"period": "weekly", "agent_id": "ops", "recipient": "a@x.com"},
    )
    assert r.status_code == 404


def test_export_returns_csv_per_user(client, monkeypatch):  # 场景 81 (CSV)
    monkeypatch.setattr(
        api,
        "fetch_traces",
        lambda **kw: [{"user_id": "alice", "total_tokens": 100, "ts": "2026-06-01T00:00:00"}],
    )
    token, _ = _session_for("admin")
    r = client.post("/admin/stats/export?view=per-user", headers=_hdr(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert "user_id" in body.splitlines()[0]
    assert "alice" in body
    detail = next(a for a in audit.search_audit() if a["action"] == "stats_export")["detail"]
    assert detail["view"] == "per-user"


def test_stats_overview_uses_real_traces(real_client):  # task 2.1 red -> green
    provider_admin_store.add_provider(
        "provider-a",
        base_url="https://example.invalid/v1",
        model="gpt-5.5",
        api_key="sk-test",
    )
    provider_admin_store.set_pricing("provider-a", input_price=1.0, output_price=2.0)
    # Anchor traces to "now" rather than a fixed calendar date: the overview
    # endpoint defaults to a 7d window relative to the wall clock, so a hardcoded
    # past date silently falls out of the window once enough real time elapses.
    recent = datetime.now(UTC) - timedelta(minutes=5)
    trace_store.record_trace_event(
        TraceEvent(
            id="trace-run-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={
                "tokens": {"prompt": 100, "completion": 100, "total": 200},
                "elapsed_s": 1.5,
                "rounds": 2,
                "model_used": "gpt-5.5",
            },
            user_id="user-1",
            session_id="sess-1",
            agent_name="ops",
            ts=recent,
        )
    )
    trace_store.record_trace_event(
        TraceEvent(
            id="trace-approval-1",
            run_id="run-1",
            event_type="permission_resolved",
            payload={"decision": "approved"},
            user_id="user-1",
            session_id="sess-1",
            agent_name="ops",
            ts=recent + timedelta(seconds=1),
        )
    )
    token, _ = _session_for("admin")

    response = real_client.get("/admin/stats/agents/ops/overview", headers=_hdr(token))

    assert response.status_code == 200
    body = response.json()
    assert body["usage"]["calls"] == 1
    assert body["usage"]["total_tokens"] == 200
    assert body["approvals"]["triggered"] == 1
    assert body["approvals"]["pass_rate"] == 1.0
    assert body["cost"]["status"] == "ok"
    assert body["cost"]["by_model"]["gpt-5.5"]["cost"] == 0.3
