"""Admin CLI integration tests for shared memory.

Updated for shared-memory-lib (3c): patches inject set_shared_memory_db
instead of store.database.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _run_admin(*args: str) -> tuple[str, str, int]:
    from fleetent.platform.admin_cli.main import main as admin_cli_main

    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            admin_cli_main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def _patch_shared_db(monkeypatch: Any, tmp_path: Path) -> None:
    from fleetent.memory import shared
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    sm_db = scope.open_shared_memory_db(MIGRATIONS)

    class _NullBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            pass

        async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[Any]:
            return []

        async def delete(self, id: str, namespace: str) -> None:
            pass

        async def clear_namespace(self, namespace: str) -> None:
            pass

    monkeypatch.setattr(shared, "_shared_memory_db", sm_db)
    monkeypatch.setattr(shared, "_shared_memory_vector_backend", _NullBackend())


def test_admin_cli_can_create_list_update_and_archive_shared_memory(
    monkeypatch: Any, tmp_path: Path
) -> None:
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
