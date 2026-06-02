"""Tests for stats_admin_api (/admin/stats, read-only). Covers scenarios 74-85."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.audit_log as audit
import fleetent.auth as auth
import fleetent.stats_admin_api as api
import fleetent.user_store as user_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
    monkeypatch.setattr(api, "fetch_traces", lambda **kw: [])
    monkeypatch.setattr(api, "fetch_approvals", lambda agent_id=None: [])
    monkeypatch.setattr(api, "agent_allowed_tools", lambda aid: [])
    monkeypatch.setattr(api, "pricing_table", lambda: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


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


def test_export_and_report_audited(client):  # 场景 81
    token, _ = _session_for("admin")
    assert client.post("/admin/stats/export", headers=_hdr(token)).status_code == 200
    r = client.post(
        "/admin/stats/reports",
        headers=_hdr(token),
        json={"period": "weekly", "agent_id": "ops", "recipient": "a@x.com"},
    )
    assert r.status_code == 200
    actions = {a["action"] for a in audit.search_audit()}
    assert {"stats_export", "stats_report_config"} <= actions


def test_viewer_cannot_configure_report(client):
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/stats/reports",
        headers=_hdr(token),
        json={"period": "weekly", "agent_id": "ops", "recipient": "a@x.com"},
    )
    assert r.status_code == 403
