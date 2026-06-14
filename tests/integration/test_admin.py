from io import StringIO
from unittest.mock import patch

import pytest

import fleetent.agent_store as agent_store
from fleetent import user_store
from fleetent.platform.admin_cli.main import main as admin_cli_main
from fleetent.platform.im_gateway_management import identity as im_user_store
from tests.integration.test_migrations import apply_migrations


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "users.db"
    apply_migrations(db)  # agent_store reads DATABASE_URL via the db boundary
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def run_admin(*args: str) -> tuple[str, str, int]:
    """Run admin CLI with given CLI args. Returns (stdout, stderr, exit_code)."""
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent-admin", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            admin_cli_main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def test_admin_platform_entrypoint_is_importable():
    assert callable(admin_cli_main)


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
    user, old_key = user_store.create_user("Eve")
    out, _, code = run_admin("rotate-key", "--user-id", user.id)
    assert code == 0
    assert "ma-" in out
    # old key is revoked after rotation
    assert user_store.get_by_api_key(old_key) is None


def test_rotate_key_not_found_exits_nonzero():
    _, err, code = run_admin("rotate-key", "--user-id", "00000000-0000-0000-0000-000000000000")
    assert code != 0
    assert "not found" in err.lower() or "error" in err.lower()


# --- allowlist admin commands ---


def test_list_pending_command_removed():
    _, err, code = run_admin("list-pending")
    assert code != 0
    assert "invalid choice" in err.lower()


def test_approve_user_command_removed():
    _, err, code = run_admin("approve-user", "--im-user-id", "1")
    assert code != 0
    assert "invalid choice" in err.lower()


def test_block_user_is_deprecated_noop():
    u = im_user_store.get_or_create("slack", "U_BLOCK", "default")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    _, err, code = run_admin("block-user", "--im-user-id", str(im_id))
    assert code == 0
    assert "deprecated" in err.lower()
    assert user_store.get_by_id(u.id).status == "active"


def test_seed_builtin_admin():
    out, _, code = run_admin("seed-builtin-admin")
    assert code == 0
    assert "initial_password" in out
    # second run is a no-op
    out2, _, code2 = run_admin("seed-builtin-admin")
    assert code2 == 0
    assert "already exists" in out2


# --- removed channel agent admin commands ---


def test_removed_channel_assign_command():
    cmd = "assign" + "-channel"
    _, err, code = run_admin(
        cmd, "--platform", "slack", "--channel-id", "C42", "--agent-name", "mybot"
    )
    assert code != 0
    assert "invalid choice" in err.lower()


def test_removed_channel_unassign_command():
    cmd = "unassign" + "-channel"
    _, err, code = run_admin(cmd, "--platform", "telegram", "--channel-id", "G7")
    assert code != 0
    assert "invalid choice" in err.lower()


# --- update-agent / version commands ---


def test_update_agent_creates_and_activates_new_version():
    agent_store.create_agent("verbot", "v1 prompt.", ["calculate"])
    out, _, code = run_admin(
        "update-agent", "--agent-name", "verbot", "--system-prompt", "v2 prompt."
    )
    assert code == 0
    versions = agent_store.list_versions("verbot")
    assert [v.version for v in versions] == [2, 1]
    active = next(v for v in versions if v.is_active)
    assert active.version == 2
    assert active.system_prompt == "v2 prompt."


def test_update_agent_no_activate_keeps_old_active():
    agent_store.create_agent("verbot2", "v1 prompt.", ["calculate"])
    out, _, code = run_admin(
        "update-agent",
        "--agent-name",
        "verbot2",
        "--system-prompt",
        "v2 prompt.",
        "--no-activate",
    )
    assert code == 0
    active = next(v for v in agent_store.list_versions("verbot2") if v.is_active)
    assert active.version == 1


def test_list_agent_versions_outputs_fields():
    agent_store.create_agent("listbot", "v1.", [])
    agent_store.create_version("listbot", system_prompt="v2.")
    out, _, code = run_admin("list-agent-versions", "--agent-name", "listbot")
    assert code == 0
    assert "2" in out and "1" in out
    # active marker for current active version
    assert "active" in out.lower()


def test_activate_agent_version_switches():
    agent_store.create_agent("actbot", "v1.", [])
    agent_store.create_version("actbot", system_prompt="v2.")
    out, _, code = run_admin("activate-agent-version", "--agent-name", "actbot", "--version", "1")
    assert code == 0
    active = next(v for v in agent_store.list_versions("actbot") if v.is_active)
    assert active.version == 1


def test_activate_agent_version_unknown_exits_nonzero():
    agent_store.create_agent("actbot2", "v1.", [])
    _, err, code = run_admin("activate-agent-version", "--agent-name", "actbot2", "--version", "99")
    assert code != 0


def test_show_agent_outputs_active_version():
    agent_store.create_agent("showbot", "show prompt.", ["calculate"])
    out, _, code = run_admin("show-agent", "--agent-name", "showbot")
    assert code == 0
    assert "showbot" in out
    assert "show prompt." in out


# --- assign-user / unassign-user commands ---


def test_assign_user():
    ag = agent_store.create_agent("userbot", "Bot.", [])
    out, _, code = run_admin("assign-user", "--user-id", "u-7", "--agent-name", "userbot")
    assert code == 0
    bound = agent_store.get_agent_for_user("u-7")
    assert bound is not None and bound.id == ag.id


def test_assign_user_agent_not_found_exits_nonzero():
    _, err, code = run_admin("assign-user", "--user-id", "u-7", "--agent-name", "ghost")
    assert code != 0


def test_unassign_user():
    ag = agent_store.create_agent("userbot2", "Bot.", [])
    agent_store.assign_user("u-8", ag.id)
    out, _, code = run_admin("unassign-user", "--user-id", "u-8", "--agent-name", "userbot2")
    assert code == 0
    assert agent_store.get_agent_for_user("u-8") is None


# --- set-default-agent command ---


def _write_agent_yaml(agents_dir, name, *, default=False):
    import yaml

    import fleetent.agent_config as agent_config

    d = agents_dir / name
    d.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
    }
    if default:
        data["bindings"] = {"default": True}
    (d / "agent.yaml").write_text(yaml.safe_dump(data))


def _read_default(agents_dir, name):
    import yaml

    data = yaml.safe_load((agents_dir / name / "agent.yaml").read_text()) or {}
    return bool((data.get("bindings") or {}).get("default", False))


def test_set_default_agent_writes_agent_yaml(tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    _write_agent_yaml(agents_dir, "basic")
    _write_agent_yaml(agents_dir, "ops", default=True)
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))

    out, _, code = run_admin("set-default-agent", "--agent-name", "basic")

    assert code == 0
    assert _read_default(agents_dir, "basic") is True
    assert _read_default(agents_dir, "ops") is False  # previous default cleared
    assert not (tmp_path / "settings.yaml").exists()


def test_set_default_agent_unknown_agent_errors(tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    _write_agent_yaml(agents_dir, "basic")
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))

    _, err, code = run_admin("set-default-agent", "--agent-name", "ghost")

    assert code != 0
    assert "ghost" in err


def test_set_default_agent_clear(tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    _write_agent_yaml(agents_dir, "ops", default=True)
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))

    out, _, code = run_admin("set-default-agent", "--clear")

    assert code == 0
    assert _read_default(agents_dir, "ops") is False


# schedule admin commands removed (agent-owned-scheduled-tasks): scheduling is
# agent-runtime-owned; manage via the agent `schedule` tool, not the platform CLI.


def test_kb_connectors_list_outputs_configured_connectors(monkeypatch):
    from fleetent.knowledge_base import operations

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
    from fleetent.knowledge_base import operations

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
    from fleetent.knowledge_base import operations

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
    from fleetent.knowledge_base import operations

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
    from fleetent.knowledge_base import operations

    async def run_connector_sync(connector_id: str, *, dry_run: bool = False):
        return operations.ConnectorSyncResult(
            connector_id=connector_id,
            status="sync_failed",
            summary={"failed": 1},
            error="token secret-value failed",
        )

    monkeypatch.setattr(operations, "run_connector_sync", run_connector_sync)

    out, _, code = run_admin("kb", "connectors", "sync", "eng-drive", "--dry-run")

    assert code == 0
    assert "sync_failed" in out
    assert "secret-value" not in out


def test_kb_extract_entities_outputs_sanitized_summary(monkeypatch):
    from fleetent.knowledge_base.extraction_store import KnowledgeExtractionRun
    from fleetent.platform.admin_cli import kb_connectors

    async def run_entity_extraction(
        tenant_id: str,
        kb_id: str,
        document_id: str | None = None,
    ):
        assert tenant_id == "default"
        assert kb_id == "engineering"
        assert document_id == "doc-1"
        return KnowledgeExtractionRun(
            id="run-secret-value",
            tenant_id=tenant_id,
            kb_id=kb_id,
            document_id=document_id,
            extractor="deterministic",
            status="succeeded",
            documents_scanned=1,
            chunks_scanned=2,
            entities_upserted=3,
            mentions_written=3,
            relations_written=1,
            failed_count=0,
        )

    monkeypatch.setattr(kb_connectors, "run_entity_extraction", run_entity_extraction)

    out, _, code = run_admin(
        "kb",
        "extract-entities",
        "--kb-id",
        "engineering",
        "--document-id",
        "doc-1",
    )

    assert code == 0
    assert "status=succeeded" in out
    assert "documents_scanned=1" in out
    assert "relations_written=1" in out
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
                    agent_name="agent-1",
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
    assert query.agent_name == "agent-1"
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
    assert query.agent_name == "agent-1"
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
    assert query.agent_name == "agent-1"
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


# --- im-connector / im-channel CLI (IM gateway management) --------------------


def _seed_slack_connector():
    import fleetent.platform.im_gateway_management.connector_store as store
    import fleetent.user_store as user_store

    store.upsert_connector(
        user_store.admin_owner_id(), "slack", config='{"bot_token": "xoxb-secret123"}', enabled=True
    )


def test_im_connector_list_shows_masked_config():
    _seed_slack_connector()

    out, _, code = run_admin("im-connector", "list")

    assert code == 0
    assert "slack" in out
    assert "t123" in out  # last 4 retained
    assert "xoxb-secret" not in out  # raw token never printed


def test_im_connector_enable_disable_toggles_flag():
    import fleetent.platform.im_gateway_management.connector_store as store
    import fleetent.user_store as user_store

    owner = user_store.admin_owner_id()
    _seed_slack_connector()

    _, _, code = run_admin("im-connector", "disable", "--platform", "slack")
    assert code == 0
    assert store.get_connector(owner, "slack")["enabled"] == 0

    _, _, code = run_admin("im-connector", "enable", "--platform", "slack")
    assert code == 0
    assert store.get_connector(owner, "slack")["enabled"] == 1


def test_im_connector_set_config_writes_config():
    import fleetent.platform.im_gateway_management.connector_config as cfg
    import fleetent.user_store as user_store

    out, _, code = run_admin(
        "im-connector", "set-config", "--platform", "slack", "--set", "bot_token=new-tok"
    )

    assert code == 0
    assert cfg.resolve(user_store.admin_owner_id(), "slack")["bot_token"] == "new-tok"


def test_seed_connectors_imports_env_tokens(monkeypatch):
    import fleetent.platform.im_gateway_management.connector_store as store
    import fleetent.user_store as user_store

    # Slack and Telegram are per-agent now; seed covers owner-level platforms (WhatsApp).
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "wa-env")

    out, _, code = run_admin("seed-connectors")

    assert code == 0
    assert "whatsapp" in out
    assert store.get_connector(user_store.admin_owner_id(), "whatsapp")["enabled"] == 1


def test_im_channel_allow_list_disallow():
    import fleetent.platform.im_gateway_management.connector_store as store
    import fleetent.user_store as user_store

    store.upsert_connector(
        user_store.admin_owner_id(), "slack", config='{"bot_token": "x"}', enabled=True
    )

    _, _, code = run_admin(
        "im-channel", "allow", "--platform", "slack", "--scope-type", "channel", "--scope-id", "C1"
    )
    assert code == 0

    out, _, code = run_admin("im-channel", "list", "--platform", "slack")
    assert code == 0
    assert "C1" in out

    import fleetent.platform.im_gateway_management.channel_allowlist as allowlist

    entry_id = allowlist.list_entries(None, "slack")[0]["id"]
    _, _, code = run_admin("im-channel", "disallow", "--id", str(entry_id))
    assert code == 0
    assert allowlist.list_entries(None, "slack") == []
