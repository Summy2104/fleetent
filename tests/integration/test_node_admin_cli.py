from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from fleetent import agent_store
from tests.integration._migration_template import apply_migrations


def _run_admin(*args: str) -> tuple[str, str, int]:
    from fleetent.platform.admin_cli.main import main as admin_cli_main

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


def test_node_admin_cli_register_list_pin_unpin_and_deregister(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)
    agent = agent_store.create_agent("ops", "Ops.", ["shell"])

    out, err, code = _run_admin(
        "node",
        "register",
        "node-a",
        "--name",
        "Node A",
        "--label",
        "region=eu",
    )
    assert code == 0
    assert err == ""
    assert "service_key: ma-" in out

    out, err, code = _run_admin("node", "list")
    assert code == 0
    assert err == ""
    assert "node-a" in out
    assert "region=eu" in out

    out, err, code = _run_admin("node", "pin", "--agent-id", str(agent.id), "--node-id", "node-a")
    assert code == 0
    assert err == ""
    assert f"agent {agent.id}" in out

    out, err, code = _run_admin("node", "deregister", "node-a")
    assert code == 1
    assert "still has pinned agents" in err

    out, err, code = _run_admin("node", "unpin", "--agent-id", str(agent.id))
    assert code == 0
    assert err == ""
    assert f"agent {agent.id}" in out

    out, err, code = _run_admin("node", "deregister", "node-a")
    assert code == 0
    assert err == ""
    assert "node-a" in out
