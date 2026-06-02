from io import StringIO
from unittest.mock import patch

import pytest

import fleetent.agent_store as agent_store
import fleetent.im_user_store as im_user_store
from fleetent import admin, user_store
from fleetent.platform.admin_cli import agents as admin_cli_agents
from fleetent.platform.admin_cli.main import main as admin_cli_main


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", db)
    monkeypatch.setattr(im_user_store, "DB_PATH", db)
    monkeypatch.setattr(agent_store, "DB_PATH", db)


def run_admin(*args: str) -> tuple[str, str, int]:
    """Run admin.main() with given CLI args. Returns (stdout, stderr, exit_code)."""
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent-admin", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            admin.main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def test_admin_platform_entrypoint_is_importable():
    assert callable(admin_cli_main)


def test_legacy_admin_entrypoint_reexports_platform_entrypoint():
    assert admin.main is admin_cli_main
    assert not hasattr(admin, "_SETTINGS_YAML")


def test_create_user_prints_id_and_key():
    out, _, code = run_admin("create-user", "--name", "Alice")
    assert code == 0
    assert "Alice" in out or "User created" in out
    assert "ma-" in out


def test_create_user_key_shown_once_note():
    out, _, _ = run_admin("create-user", "--name", "Bob")
    assert "shown once" in out


def test_list_users_empty():
    out, _, code = run_admin("list-users")
    assert code == 0
    assert "No users" in out


def test_list_users_shows_created_users():
    run_admin("create-user", "--name", "Carol")
    run_admin("create-user", "--name", "Dave")
    out, _, code = run_admin("list-users")
    assert code == 0
    assert "Carol" in out
    assert "Dave" in out


def test_rotate_key_updates_key():
    user = user_store.create_user("Eve")
    old_key = user.api_key
    out, _, code = run_admin("rotate-key", "--user-id", user.id)
    assert code == 0
    assert "ma-" in out
    refreshed = user_store.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.api_key != old_key


def test_rotate_key_not_found_exits_nonzero():
    _, err, code = run_admin("rotate-key", "--user-id", "00000000-0000-0000-0000-000000000000")
    assert code != 0
    assert "not found" in err.lower() or "error" in err.lower()


# --- allowlist admin commands ---


def test_list_pending_no_users():
    out, _, code = run_admin("list-pending")
    assert code == 0
    assert "No pending" in out


def test_new_users_not_pending_by_default():
    # v1.0 default-allow: newly created IM users are not pending.
    im_user_store.get_or_create("slack", "U_PEND1")
    im_user_store.get_or_create("telegram", "12345")
    out, _, code = run_admin("list-pending")
    assert code == 0
    assert "No pending" in out


def test_list_pending_shows_blocked_users():
    u = im_user_store.get_or_create("slack", "U_BLK")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    im_user_store.block_user(im_id)  # allowed=0 -> appears in legacy pending list
    out, _, code = run_admin("list-pending")
    assert code == 0
    assert "U_BLK" in out


def test_approve_user():
    u = im_user_store.get_or_create("slack", "U_APPROVE")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    im_user_store.block_user(im_id)
    out, _, code = run_admin("approve-user", "--im-user-id", str(im_id))
    assert code == 0
    assert im_user_store.check_allowed_by_user_id(u.id) is True


def test_approve_user_not_found_exits_nonzero():
    _, err, code = run_admin("approve-user", "--im-user-id", "9999")
    assert code != 0
    assert "not found" in err.lower() or "error" in err.lower()


def test_block_user_is_deprecated_noop():
    u = im_user_store.get_or_create("slack", "U_BLOCK")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    _, err, code = run_admin("block-user", "--im-user-id", str(im_id))
    assert code == 0
    assert "deprecated" in err.lower()
    # state unchanged: still allowed
    assert im_user_store.check_allowed_by_user_id(u.id) is True


def test_seed_builtin_admin():
    out, _, code = run_admin("seed-builtin-admin")
    assert code == 0
    assert "initial_password" in out
    # second run is a no-op
    out2, _, code2 = run_admin("seed-builtin-admin")
    assert code2 == 0
    assert "already exists" in out2


# --- channel agent admin commands ---


def test_assign_channel():
    ag = agent_store.create_agent("mybot", "Bot prompt.", [])
    out, _, code = run_admin(
        "assign-channel", "--platform", "slack", "--channel-id", "C42", "--agent-name", "mybot"
    )
    assert code == 0
    found = agent_store.get_agent_for_channel("slack", "C42")
    assert found is not None
    assert found.id == ag.id


def test_assign_channel_agent_not_found_exits_nonzero():
    _, err, code = run_admin(
        "assign-channel", "--platform", "slack", "--channel-id", "C99", "--agent-name", "ghost"
    )
    assert code != 0
    assert "not found" in err.lower() or "error" in err.lower()


def test_unassign_channel():
    ag = agent_store.create_agent("rmbot", "Rm prompt.", [])
    agent_store.assign_channel("telegram", "G7", ag.id)
    out, _, code = run_admin("unassign-channel", "--platform", "telegram", "--channel-id", "G7")
    assert code == 0
    assert agent_store.get_agent_for_channel("telegram", "G7") is None


# --- set-default-agent command ---


def test_set_default_agent(tmp_path, monkeypatch):
    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text("")
    monkeypatch.setattr(admin_cli_agents, "_SETTINGS_YAML", settings_yaml)
    agent_store.create_agent("basic", "Basic.", [])
    out, _, code = run_admin("set-default-agent", "--agent-name", "basic")
    assert code == 0
    assert "basic" in settings_yaml.read_text()


def test_set_default_agent_clear(tmp_path, monkeypatch):
    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text("default_agent_name: basic\n")
    monkeypatch.setattr(admin_cli_agents, "_SETTINGS_YAML", settings_yaml)
    out, _, code = run_admin("set-default-agent", "--clear")
    assert code == 0
    content = settings_yaml.read_text()
    assert "basic" not in content


# ── schedule admin commands ───────────────────────────────────────────────────


@pytest.fixture(autouse=False)
def tmp_sched_db(isolated_schedule_db):
    return isolated_schedule_db


def test_list_schedules_empty(tmp_sched_db):
    out, _, code = run_admin("list-schedules")
    assert code == 0
    assert "No scheduled tasks" in out


def test_add_schedule_prints_task_id(tmp_sched_db):
    out, _, code = run_admin(
        "add-schedule",
        "--name",
        "standup",
        "--cron",
        "0 9 * * 1-5",
        "--user-id",
        "u-1",
        "--message",
        "run standup",
    )
    assert code == 0
    assert len(out.strip()) == 36  # UUID printed


def test_list_schedules_shows_task(tmp_sched_db):
    run_admin(
        "add-schedule",
        "--name",
        "daily",
        "--cron",
        "0 9 * * *",
        "--user-id",
        "u-1",
        "--message",
        "go",
    )
    out, _, code = run_admin("list-schedules")
    assert code == 0
    assert "daily" in out
    assert "0 9 * * *" in out
    assert "u-1" in out


def test_remove_schedule_success(tmp_sched_db):
    out, _, _ = run_admin(
        "add-schedule", "--name", "x", "--cron", "* * * * *", "--user-id", "u-1", "--message", "hi"
    )
    task_id = out.strip()
    _, _, code = run_admin("remove-schedule", "--task-id", task_id)
    assert code == 0


def test_remove_schedule_not_found_exits_nonzero(tmp_sched_db):
    _, _, code = run_admin("remove-schedule", "--task-id", "no-such-id")
    assert code != 0


def test_kb_connectors_list_outputs_configured_connectors(monkeypatch):
    from fleetent.intelligence.knowledge_base import operations

    monkeypatch.setattr(
        operations,
        "list_configured_connectors",
        lambda: [
            operations.ConnectorSummary(
                connector_id="eng-drive",
                connector_type="google_drive",
                enabled=True,
                tenant_id="default",
                kb_id="engineering",
                scope="folder:folder-1",
                credential_ref_summary="file:google.json",
            )
        ],
    )

    out, _, code = run_admin("kb", "connectors", "list")

    assert code == 0
    assert "eng-drive" in out
    assert "google_drive" in out


def test_kb_connectors_check_outputs_status(monkeypatch):
    from fleetent.intelligence.knowledge_base import operations

    async def check_connector(connector_id: str):
        return operations.ConnectorCheckResult(
            connector_id=connector_id,
            status="ok",
            message="connector is reachable",
        )

    monkeypatch.setattr(operations, "check_connector", check_connector)

    out, _, code = run_admin("kb", "connectors", "check", "eng-drive")

    assert code == 0
    assert "ok" in out
    assert "eng-drive" in out


def test_kb_connectors_status_outputs_never_run(monkeypatch):
    from fleetent.intelligence.knowledge_base import operations

    monkeypatch.setattr(
        operations,
        "get_connector_status",
        lambda connector_id: operations.ConnectorStatus(
            connector_id=connector_id,
            connector_type="google_drive",
            tenant_id="default",
            kb_id="engineering",
            last_status="never_run",
            last_started_at=None,
            last_finished_at=None,
            last_summary={},
            last_error=None,
        ),
    )

    out, _, code = run_admin("kb", "connectors", "status", "eng-drive")

    assert code == 0
    assert "never_run" in out


def test_kb_connectors_sync_dry_run_outputs_summary(monkeypatch):
    from fleetent.intelligence.knowledge_base import operations

    async def run_connector_sync(connector_id: str, *, dry_run: bool = False):
        assert dry_run is True
        return operations.ConnectorSyncResult(
            connector_id=connector_id,
            status="dry_run_ok",
            summary={"planned": 1},
            error=None,
        )

    monkeypatch.setattr(operations, "run_connector_sync", run_connector_sync)

    out, _, code = run_admin("kb", "connectors", "sync", "eng-drive", "--dry-run")

    assert code == 0
    assert "dry_run_ok" in out
    assert "planned=1" in out


def test_kb_connectors_cli_output_is_sanitized(monkeypatch):
    from fleetent.intelligence.knowledge_base import operations

    async def run_connector_sync(connector_id: str, *, dry_run: bool = False):
        return operations.ConnectorSyncResult(
            connector_id=connector_id,
            status="sync_failed",
            summary={"failed": 1},
            error="token secret-value failed",
        )

    monkeypatch.setattr(operations, "run_connector_sync", run_connector_sync)

    out, _, code = run_admin("kb", "connectors", "sync", "eng-drive")

    assert code == 0
    assert "sync_failed" in out
    assert "secret-value" not in out


def test_diagnostics_export_cli_outputs_package_path(monkeypatch, tmp_path):
    from fleetent.observability import diagnostics

    package_path = tmp_path / "diagnostics.zip"

    def export_diagnostics(request):
        return diagnostics.DiagnosticsExportPackage(path=package_path)

    monkeypatch.setattr(diagnostics, "export_diagnostics", export_diagnostics)

    out, _, code = run_admin("diagnostics", "export", "--output-dir", str(tmp_path))

    assert code == 0
    assert str(package_path) in out


def test_diagnostics_retention_dry_run_cli_outputs_candidates(monkeypatch):
    from fleetent.observability import diagnostics

    monkeypatch.setattr(
        diagnostics,
        "plan_diagnostics_retention",
        lambda: diagnostics.DiagnosticsRetentionPlan(
            log_files=[diagnostics.Path("data/logs/old.log")],
            trace_count=3,
            diagnostic_exports=[diagnostics.Path("data/diagnostics/old.zip")],
        ),
    )

    out, _, code = run_admin("diagnostics", "retention", "dry-run")

    assert code == 0
    assert "logs=1" in out
    assert "traces=3" in out
    assert "exports=1" in out


def test_diagnostics_retention_apply_disabled_cli_exits_nonzero(monkeypatch):
    from fleetent.observability import diagnostics

    monkeypatch.setattr(
        diagnostics,
        "apply_diagnostics_retention",
        lambda: diagnostics.DiagnosticsRetentionResult(
            applied=False,
            deleted_logs=0,
            deleted_traces=0,
            deleted_exports=0,
            failures=[],
            message="diagnostics retention disabled",
        ),
    )

    _, err, code = run_admin("diagnostics", "retention", "apply")

    assert code != 0
    assert "disabled" in err


def test_diagnostics_cli_output_is_sanitized(monkeypatch, tmp_path):
    from fleetent.observability import diagnostics

    def export_diagnostics(request):
        return diagnostics.DiagnosticsExportPackage(path=tmp_path / "token-secret-value.zip")

    monkeypatch.setattr(diagnostics, "export_diagnostics", export_diagnostics)

    out, _, code = run_admin("diagnostics", "export")

    assert code == 0
    assert "secret-value" not in out


def test_observability_traces_cli_queries_public_api_and_hides_payload_values(monkeypatch):
    from datetime import datetime

    from fleetent import observability

    captured = {}

    def query_trace_events(query):
        captured["query"] = query
        return iter(
            [
                observability.TraceEvent(
                    id="evt-1",
                    ts=datetime.fromisoformat("2026-06-02T01:02:03+00:00"),
                    run_id="run-1",
                    event_type="agent_run_completed",
                    user_id="user-1",
                    agent_id="agent-1",
                    session_id="session-1",
                    payload={
                        "model_used": "claude",
                        "token": "secret-value",
                        "reply": "sensitive reply",
                    },
                )
            ]
        )

    monkeypatch.setattr(observability, "query_trace_events", query_trace_events)

    out, _, code = run_admin(
        "observability",
        "traces",
        "--run-id",
        "run-1",
        "--event-type",
        "agent_run_completed",
        "--user-id",
        "user-1",
        "--agent-id",
        "agent-1",
        "--session-id",
        "session-1",
        "--tenant-id",
        "default",
        "--from",
        "2026-06-02T00:00:00+00:00",
        "--to",
        "2026-06-02T23:59:59+00:00",
        "--limit",
        "20",
    )

    query = captured["query"]
    assert code == 0
    assert query.run_id == "run-1"
    assert query.event_type == "agent_run_completed"
    assert query.user_id == "user-1"
    assert query.agent_id == "agent-1"
    assert query.session_id == "session-1"
    assert query.tenant_id == "default"
    assert query.start_ts == datetime.fromisoformat("2026-06-02T00:00:00+00:00")
    assert query.end_ts == datetime.fromisoformat("2026-06-02T23:59:59+00:00")
    assert query.limit == 20
    assert "agent_run_completed" in out
    assert "model_used,reply,token" in out
    assert "secret-value" not in out
    assert "sensitive reply" not in out


def test_observability_usage_cli_queries_public_api_and_outputs_summary(monkeypatch):
    from datetime import datetime

    from fleetent import observability

    captured = {}

    def get_usage_summary(query):
        captured["query"] = query
        return observability.UsageSummary(
            run_count=2,
            prompt_tokens=10,
            completion_tokens=15,
            total_tokens=25,
            total_elapsed_s=3.0,
            avg_elapsed_s=1.5,
            by_model=[
                observability.ModelUsage(
                    model="claude",
                    run_count=2,
                    prompt_tokens=10,
                    completion_tokens=15,
                    total_tokens=25,
                    total_elapsed_s=3.0,
                    avg_elapsed_s=1.5,
                )
            ],
        )

    monkeypatch.setattr(observability, "get_usage_summary", get_usage_summary)

    out, _, code = run_admin(
        "observability",
        "usage",
        "--user-id",
        "user-1",
        "--agent-id",
        "agent-1",
        "--session-id",
        "session-1",
        "--tenant-id",
        "default",
        "--from",
        "2026-06-02T00:00:00+00:00",
        "--to",
        "2026-06-02T23:59:59+00:00",
        "--limit",
        "50",
    )

    query = captured["query"]
    assert code == 0
    assert query.user_id == "user-1"
    assert query.agent_id == "agent-1"
    assert query.session_id == "session-1"
    assert query.tenant_id == "default"
    assert query.start_ts == datetime.fromisoformat("2026-06-02T00:00:00+00:00")
    assert query.end_ts == datetime.fromisoformat("2026-06-02T23:59:59+00:00")
    assert query.limit == 50
    assert "run_count=2" in out
    assert "total_tokens=25" in out
    assert "model=claude" in out


def test_observability_performance_cli_queries_public_api_and_outputs_summary(monkeypatch):
    from fleetent import observability

    captured = {}

    def get_performance_summary(query):
        captured["query"] = query
        return observability.PerformanceSummary(
            run_count=4,
            completed_count=3,
            failed_count=1,
            failure_rate=0.25,
            avg_elapsed_s=2.0,
            p50_elapsed_s=1.5,
            p95_elapsed_s=4.0,
            llm_call_count=5,
            llm_error_count=1,
            avg_llm_elapsed_s=0.8,
            p95_llm_elapsed_s=1.4,
            fallback_count=1,
            fallback_rate=0.25,
            tool_call_count=3,
            tool_error_count=1,
            avg_tool_elapsed_s=0.6,
            p95_tool_elapsed_s=1.1,
            permission_requested_count=2,
            permission_approved_count=1,
            permission_rejected_count=0,
            permission_timeout_count=1,
            avg_permission_wait_s=5.0,
            by_model=[
                observability.ModelPerformance(
                    model="claude",
                    call_count=5,
                    error_count=1,
                    avg_elapsed_s=0.8,
                )
            ],
            by_tool=[
                observability.ToolPerformance(
                    tool_name="search",
                    call_count=3,
                    error_count=1,
                    avg_elapsed_s=0.6,
                )
            ],
            permission=observability.PermissionSummary(
                requested_count=2,
                approved_count=1,
                rejected_count=0,
                timeout_count=1,
                avg_wait_s=5.0,
            ),
        )

    monkeypatch.setattr(observability, "get_performance_summary", get_performance_summary)

    out, _, code = run_admin(
        "observability",
        "performance",
        "--agent-id",
        "agent-1",
        "--limit",
        "100",
    )

    query = captured["query"]
    assert code == 0
    assert query.agent_id == "agent-1"
    assert query.limit == 100
    assert "run_count=4" in out
    assert "failure_rate=0.250" in out
    assert "llm_calls=5" in out
    assert "tool_calls=3" in out
    assert "fallbacks=1" in out
    assert "permission_requested=2" in out
    assert "model=claude" in out
    assert "tool=search" in out


def test_observability_cli_invalid_time_exits_nonzero():
    _, err, code = run_admin("observability", "usage", "--from", "not-a-time")

    assert code != 0
    assert "invalid timestamp" in err
