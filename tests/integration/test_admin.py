from io import StringIO
from unittest.mock import patch

import pytest

import fleetent.agent_store as agent_store
import fleetent.im_user_store as im_user_store
from fleetent import admin, user_store


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
    monkeypatch.setattr(admin, "_SETTINGS_YAML", settings_yaml)
    agent_store.create_agent("basic", "Basic.", [])
    out, _, code = run_admin("set-default-agent", "--agent-name", "basic")
    assert code == 0
    assert "basic" in settings_yaml.read_text()


def test_set_default_agent_clear(tmp_path, monkeypatch):
    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text("default_agent_name: basic\n")
    monkeypatch.setattr(admin, "_SETTINGS_YAML", settings_yaml)
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
