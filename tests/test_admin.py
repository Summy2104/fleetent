from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from fleetent import admin, user_store
import fleetent.im_user_store as im_user_store
import fleetent.agent_store as agent_store


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


def test_list_pending_shows_unapproved_users():
    im_user_store.get_or_create("slack", "U_PEND1")
    im_user_store.get_or_create("telegram", "12345")
    out, _, code = run_admin("list-pending")
    assert code == 0
    assert "U_PEND1" in out
    assert "12345" in out


def test_approve_user():
    im_user_store.get_or_create("slack", "U_APPROVE")
    pending = im_user_store.list_pending()
    im_user_id = str(pending[0]["id"])
    out, _, code = run_admin("approve-user", "--im-user-id", im_user_id)
    assert code == 0
    assert im_user_store.list_pending() == []


def test_approve_user_not_found_exits_nonzero():
    _, err, code = run_admin("approve-user", "--im-user-id", "9999")
    assert code != 0
    assert "not found" in err.lower() or "error" in err.lower()


def test_block_user():
    im_user_store.get_or_create("slack", "U_BLOCK")
    pending = im_user_store.list_pending()
    im_user_id = str(pending[0]["id"])
    run_admin("approve-user", "--im-user-id", im_user_id)
    assert im_user_store.list_pending() == []
    out, _, code = run_admin("block-user", "--im-user-id", im_user_id)
    assert code == 0
    assert len(im_user_store.list_pending()) == 1


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

import fleetent.schedule_store as schedule_store_mod


@pytest.fixture(autouse=False)
def tmp_sched_db(tmp_path, monkeypatch):
    db = tmp_path / "sched.db"
    monkeypatch.setattr(schedule_store_mod, "DB_PATH", db)
    return db


def test_list_schedules_empty(tmp_sched_db):
    out, _, code = run_admin("list-schedules")
    assert code == 0
    assert "No scheduled tasks" in out


def test_add_schedule_prints_task_id(tmp_sched_db):
    out, _, code = run_admin(
        "add-schedule",
        "--name", "standup",
        "--cron", "0 9 * * 1-5",
        "--user-id", "u-1",
        "--message", "run standup",
    )
    assert code == 0
    assert len(out.strip()) == 36  # UUID printed


def test_list_schedules_shows_task(tmp_sched_db):
    run_admin("add-schedule", "--name", "daily", "--cron", "0 9 * * *",
              "--user-id", "u-1", "--message", "go")
    out, _, code = run_admin("list-schedules")
    assert code == 0
    assert "daily" in out
    assert "0 9 * * *" in out
    assert "u-1" in out


def test_remove_schedule_success(tmp_sched_db):
    out, _, _ = run_admin("add-schedule", "--name", "x", "--cron", "* * * * *",
                           "--user-id", "u-1", "--message", "hi")
    task_id = out.strip()
    _, _, code = run_admin("remove-schedule", "--task-id", task_id)
    assert code == 0


def test_remove_schedule_not_found_exits_nonzero(tmp_sched_db):
    _, _, code = run_admin("remove-schedule", "--task-id", "no-such-id")
    assert code != 0
