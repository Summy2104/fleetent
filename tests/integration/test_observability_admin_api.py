from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.observability_management.observability_admin_api as api
import fleetent.user_store as user_store
from fleetent import observability
from fleetent.server import app
from tests.integration._migration_template import apply_migrations


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    apply_migrations(db_path)
    return TestClient(app, raise_server_exceptions=True)


def _session_header(role: str) -> dict[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    token = auth.create_session(user.id)
    return {"Authorization": f"Session {token}"}


def test_observability_routes_exist(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/admin/observability/traces")

    assert response.status_code != 404


def test_traces_filter_by_run_id(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    captured: dict[str, observability.TraceQuery] = {}

    def _query(query: observability.TraceQuery) -> list[observability.TraceEvent]:
        captured["query"] = query
        return [
            observability.TraceEvent(
                id="trace-1",
                run_id="run-1",
                event_type="tool_call",
                payload={"tool_name": "shell"},
                session_id="sess-1",
                user_id="user-1",
                agent_name="ops-bot",
                tenant_id="tenant-1",
                ts=datetime(2026, 6, 18, 8, 0, tzinfo=UTC),
            )
        ]

    monkeypatch.setattr(api.observability, "query_trace_events", _query)

    response = client.get(
        "/admin/observability/traces?run_id=run-1",
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    assert captured["query"].run_id == "run-1"
    assert response.json()[0]["run_id"] == "run-1"


def test_traces_multi_filter(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    captured: dict[str, observability.TraceQuery] = {}

    def _query(query: observability.TraceQuery) -> list[observability.TraceEvent]:
        captured["query"] = query
        return []

    monkeypatch.setattr(api.observability, "query_trace_events", _query)

    response = client.get(
        "/admin/observability/traces",
        params={
            "user_id": "user-1",
            "agent": "ops-bot",
            "session_id": "sess-1",
            "tenant_id": "tenant-1",
            "event_type": "tool_call",
            "since": "2026-06-18T08:00:00+00:00",
            "until": "2026-06-18T09:00:00+00:00",
            "limit": 50,
        },
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    query = captured["query"]
    assert query.user_id == "user-1"
    assert query.agent_name == "ops-bot"
    assert query.session_id == "sess-1"
    assert query.tenant_id == "tenant-1"
    assert query.event_type == "tool_call"
    assert query.start_ts == datetime(2026, 6, 18, 8, 0, tzinfo=UTC)
    assert query.end_ts == datetime(2026, 6, 18, 9, 0, tzinfo=UTC)
    assert query.limit == 50


def test_usage_by_agent(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    captured: dict[str, observability.UsageQuery] = {}

    def _summary(query: observability.UsageQuery) -> observability.UsageSummary:
        captured["query"] = query
        return observability.UsageSummary(
            run_count=2,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            total_elapsed_s=3.0,
            avg_elapsed_s=1.5,
            by_model=[
                observability.ModelUsage(
                    model="gpt-5.5",
                    run_count=2,
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    total_elapsed_s=3.0,
                    avg_elapsed_s=1.5,
                )
            ],
        )

    monkeypatch.setattr(api.observability, "get_usage_summary", _summary)

    response = client.get(
        "/admin/observability/usage",
        params={"agent": "ops-bot", "since": "2026-06-18T08:00:00+00:00"},
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    assert captured["query"].agent_name == "ops-bot"
    assert captured["query"].start_ts == datetime(2026, 6, 18, 8, 0, tzinfo=UTC)
    body = response.json()
    assert body["run_count"] == 2
    assert body["by_model"][0]["model"] == "gpt-5.5"


def test_performance_metrics(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    captured: dict[str, observability.PerformanceQuery] = {}

    def _summary(query: observability.PerformanceQuery) -> observability.PerformanceSummary:
        captured["query"] = query
        return observability.PerformanceSummary(
            run_count=4,
            completed_count=3,
            failed_count=1,
            failure_rate=0.25,
            avg_elapsed_s=2.5,
            p50_elapsed_s=2.0,
            p95_elapsed_s=4.0,
            llm_call_count=5,
            llm_error_count=1,
            avg_llm_elapsed_s=0.8,
            p95_llm_elapsed_s=1.2,
            fallback_count=1,
            fallback_rate=0.25,
            tool_call_count=3,
            tool_error_count=1,
            avg_tool_elapsed_s=0.5,
            p95_tool_elapsed_s=0.9,
            permission_requested_count=2,
            permission_approved_count=1,
            permission_rejected_count=1,
            permission_timeout_count=0,
            avg_permission_wait_s=4.0,
            by_model=[
                observability.ModelPerformance(
                    model="gpt-5.5",
                    call_count=5,
                    error_count=1,
                    avg_elapsed_s=0.8,
                )
            ],
            by_tool=[
                observability.ToolPerformance(
                    tool_name="shell",
                    call_count=3,
                    error_count=1,
                    avg_elapsed_s=0.5,
                )
            ],
            permission=observability.PermissionSummary(
                requested_count=2,
                approved_count=1,
                rejected_count=1,
                timeout_count=0,
                avg_wait_s=4.0,
            ),
        )

    monkeypatch.setattr(api.observability, "get_performance_summary", _summary)

    response = client.get(
        "/admin/observability/performance",
        params={"agent": "ops-bot", "since": "2026-06-18T08:00:00+00:00"},
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    assert captured["query"].agent_name == "ops-bot"
    body = response.json()
    assert body["p50_elapsed_s"] == 2.0
    assert body["permission"]["approved_count"] == 1
    assert body["by_tool"][0]["tool_name"] == "shell"


def test_non_admin_returns_403(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/admin/observability/traces", headers=_session_header("viewer"))

    assert response.status_code == 403
