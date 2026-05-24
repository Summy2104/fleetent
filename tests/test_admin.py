from io import StringIO
from unittest.mock import patch

import pytest

from mini_agent import admin, user_store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")


def run_admin(*args: str) -> tuple[str, str, int]:
    """Run admin.main() with given CLI args. Returns (stdout, stderr, exit_code)."""
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["mini-agent-admin", *args]),
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
