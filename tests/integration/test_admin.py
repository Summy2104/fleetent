from io import StringIO
from unittest.mock import patch

import pytest

from fleetent.platform.platform_cli.main import main as platform_cli_main
from tests.integration.test_migrations import apply_migrations


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def run_platform(*args: str) -> tuple[str, str, int]:
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            platform_cli_main()
        except SystemExit as e:
            exit_code = int(e.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def test_platform_entrypoint_is_importable():
    assert callable(platform_cli_main)


def test_seed_builtin_admin():
    out, _, code = run_platform("seed-builtin-admin")
    assert code == 0
    assert "initial_password" in out

    out2, _, code2 = run_platform("seed-builtin-admin")
    assert code2 == 0
    assert "already exists" in out2


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (("create-user", "--name", "Alice"), "create-user"),
        (("rotate-key", "--user-id", "u1"), "rotate-key"),
        (("block-user", "--im-user-id", "1"), "block-user"),
        (("update-agent", "--agent-name", "ops"), "update-agent"),
        (("assign-user", "--user-id", "u1", "--agent-name", "ops"), "assign-user"),
        (("set-default-agent", "--agent-name", "ops"), "set-default-agent"),
        (("kb", "connectors", "list"), "connectors"),
        (("observability", "traces"), "observability"),
    ],
)
def test_removed_platform_commands_exit_with_invalid_choice(args: tuple[str, ...], needle: str):
    _, err, code = run_platform(*args)

    assert code != 0
    assert "invalid choice" in err.lower()
    assert needle in err


def test_list_pending_command_removed():
    _, err, code = run_platform("list-pending")
    assert code != 0
    assert "invalid choice" in err.lower()


def test_approve_user_command_removed():
    _, err, code = run_platform("approve-user", "--im-user-id", "1")
    assert code != 0
    assert "invalid choice" in err.lower()


def test_removed_channel_assign_command():
    cmd = "assign" + "-channel"
    _, err, code = run_platform(
        cmd, "--platform", "slack", "--channel-id", "C42", "--agent-name", "mybot"
    )
    assert code != 0
    assert "invalid choice" in err.lower()


def test_removed_channel_unassign_command():
    cmd = "unassign" + "-channel"
    _, err, code = run_platform(cmd, "--platform", "telegram", "--channel-id", "G7")
    assert code != 0
    assert "invalid choice" in err.lower()
