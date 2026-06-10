"""Unit tests for the IM connector registry (agent-owned-scheduled-tasks)."""

import fleetent.im_gateway.connector_registry as reg


def test_register_and_snapshot_for_agent():
    reg._clear()
    slack_conn = object()
    tg_conn = object()
    reg.register("slack", "bot-a", slack_conn)
    reg.register("telegram", "bot-a", tg_conn)
    reg.register("slack", "bot-b", object())

    snap = reg.snapshot("bot-a")
    assert snap == {"slack": slack_conn, "telegram": tg_conn}


def test_unregister_is_idempotent():
    reg._clear()
    reg.register("slack", "bot-a", object())
    reg.unregister("slack", "bot-a")
    reg.unregister("slack", "bot-a")  # no raise on repeat
    assert reg.snapshot("bot-a") == {}


def test_snapshot_isolates_by_agent():
    reg._clear()
    reg.register("slack", "bot-a", object())
    assert reg.snapshot("bot-b") == {}
