from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from fleetent.platform.admin_cli.main import main as admin_cli_main


def _run_admin(*args: str) -> tuple[str, str, int]:
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


def test_node_cli_dispatches_register_list_deregister_pin_and_unpin(monkeypatch) -> None:
    from fleetent.platform.admin_cli import nodes

    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        nodes.node_store,
        "register_node",
        lambda node_id, **kwargs: (
            calls.append(("register", (node_id,), kwargs))
            or (
                "ma-" + "a" * 64,
                {
                    "id": node_id,
                    "name": kwargs.get("name"),
                    "labels": kwargs.get("labels", {}),
                    "registered_at": "2026-06-16T00:00:00+00:00",
                    "last_seen_at": None,
                },
            )
        ),
    )
    monkeypatch.setattr(
        nodes.node_store,
        "list_nodes",
        lambda: [
            {
                "id": "node-a",
                "name": "Node A",
                "labels": {"region": "eu"},
                "registered_at": "2026-06-16T00:00:00+00:00",
                "last_seen_at": None,
            }
        ],
    )
    monkeypatch.setattr(
        nodes.node_store,
        "deregister_node",
        lambda node_id: calls.append(("deregister", (node_id,), {})),
    )
    monkeypatch.setattr(
        nodes.placement_store,
        "pin_agent",
        lambda agent_id, node_id, **kwargs: (
            calls.append(("pin", (agent_id, node_id), kwargs))
            or {"agent_id": agent_id, "node_id": node_id, "pinned_by": kwargs.get("pinned_by")}
        ),
    )
    monkeypatch.setattr(
        nodes.placement_store,
        "unpin_agent",
        lambda agent_id: calls.append(("unpin", (agent_id,), {})),
    )

    out, err, code = _run_admin(
        "node",
        "register",
        "node-a",
        "--name",
        "Node A",
        "--label",
        "region=eu",
        "--label",
        "tier=prod",
    )
    assert code == 0
    assert err == ""
    assert "service_key: ma-" in out

    out, err, code = _run_admin("node", "list")
    assert code == 0
    assert err == ""
    assert "node-a" in out
    assert "region=eu" in out

    out, err, code = _run_admin(
        "node", "pin", "--agent-id", "7", "--node-id", "node-a", "--by", "ops"
    )
    assert code == 0
    assert err == ""
    assert "agent 7" in out

    out, err, code = _run_admin("node", "unpin", "--agent-id", "7")
    assert code == 0
    assert err == ""
    assert "agent 7" in out

    out, err, code = _run_admin("node", "deregister", "node-a")
    assert code == 0
    assert err == ""
    assert "node-a" in out

    assert (
        "register",
        ("node-a",),
        {"name": "Node A", "labels": {"region": "eu", "tier": "prod"}},
    ) in calls
    assert ("deregister", ("node-a",), {}) in calls
    assert ("pin", (7, "node-a"), {"pinned_by": "ops"}) in calls
    assert ("unpin", (7,), {}) in calls
