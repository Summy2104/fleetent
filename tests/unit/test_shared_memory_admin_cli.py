from io import StringIO
from unittest.mock import patch

from fleetent.db import create_database
from fleetent.platform.admin_cli.main import main as admin_cli_main


def _run_admin(*args: str) -> tuple[str, str, int]:
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent-admin", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            admin_cli_main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def _patch_shared_db(monkeypatch, tmp_path):
    from fleetent.intelligence.memory import store
    from tests.integration.test_migrations import apply_migrations

    db_path = tmp_path / "shared-memory-cli.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(store, "database", lambda: database)


def test_admin_cli_can_create_list_update_and_archive_shared_memory(monkeypatch, tmp_path):
    _patch_shared_db(monkeypatch, tmp_path)
    from fleetent.platform.admin_cli import shared_memory

    audit_events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        shared_memory,
        "record_shared_memory_admin_audit",
        lambda action, item_id, actor: audit_events.append((action, actor)),
    )

    out, _, code = _run_admin(
        "memory",
        "shared",
        "create",
        "--scope-type",
        "team",
        "--scope-id",
        "eng",
        "--type",
        "context",
        "--content",
        "Team prefers short release notes.",
        "--actor",
        "admin",
    )
    assert code == 0
    assert "shared_memory_id=" in out
    item_id = out.strip().split("shared_memory_id=", 1)[1].split()[0]

    out, _, code = _run_admin(
        "memory", "shared", "list", "--scope-type", "team", "--scope-id", "eng"
    )
    assert code == 0
    assert item_id in out
    assert "Team prefers short release notes." in out

    out, _, code = _run_admin(
        "memory",
        "shared",
        "update",
        item_id,
        "--content",
        "Team prefers concise release notes.",
        "--actor",
        "admin",
    )
    assert code == 0
    assert item_id in out

    out, _, code = _run_admin("memory", "shared", "archive", item_id, "--actor", "admin")
    assert code == 0
    assert "status=archived" in out
    assert audit_events == [
        ("shared_memory.create", "admin"),
        ("shared_memory.update", "admin"),
        ("shared_memory.archive", "admin"),
    ]
