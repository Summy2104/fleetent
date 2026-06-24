"""Tests for fleetent platform upgrade command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from fleetent.platform.platform_cli.main import main as platform_cli_main


def _run_platform(*args: str) -> tuple[str, str, int]:
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            platform_cli_main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def test_upgrade_dry_run_delegates_to_upgrade_script(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_upgrade_main(
        argv: list[str] | None = None,
        stdout=None,
        stderr=None,
    ) -> int:
        calls.append({"argv": list(argv or []), "stdout": stdout, "stderr": stderr})
        return 0

    import fleetent.platform.platform_cli.upgrade as upgrade_module

    monkeypatch.setattr(upgrade_module, "_upgrade_main", fake_upgrade_main)

    out, err, code = _run_platform("upgrade", "--dry-run")

    assert code == 0
    assert len(calls) == 1
    assert "--dry-run" in calls[0]["argv"]


def test_upgrade_passthrough_backup_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_upgrade_main(argv=None, stdout=None, stderr=None) -> int:
        calls.append(list(argv or []))
        return 0

    import fleetent.platform.platform_cli.upgrade as upgrade_module

    monkeypatch.setattr(upgrade_module, "_upgrade_main", fake_upgrade_main)

    _run_platform("upgrade", "--backup-dir", "/tmp/backups", "--backup-only")

    assert len(calls) == 1
    assert "--backup-dir" in calls[0]
    assert "/tmp/backups" in calls[0]
    assert "--backup-only" in calls[0]


def test_upgrade_passes_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_upgrade_main(argv=None, stdout=None, stderr=None) -> int:
        calls.append(list(argv or []))
        return 0

    import fleetent.platform.platform_cli.upgrade as upgrade_module

    monkeypatch.setattr(upgrade_module, "_upgrade_main", fake_upgrade_main)

    _run_platform("upgrade", "--database-url", "sqlite:///data/management.db")

    assert "--database-url" in calls[0]
    assert "sqlite:///data/management.db" in calls[0]


def test_upgrade_exit_code_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    import fleetent.platform.platform_cli.upgrade as upgrade_module

    monkeypatch.setattr(upgrade_module, "_upgrade_main", lambda **_: 1)

    _, _, code = _run_platform("upgrade")

    assert code == 1
