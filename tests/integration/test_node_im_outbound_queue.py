from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from fleetent.db import SQLiteDatabase
from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredState
from fleetent.schema_migrations import migrate


def _config(tmp_path: Path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _agent_state_db(
    tmp_path: Path, *, tenant_id: str = "tenant-1", agent_id: int = 101
) -> SQLiteDatabase:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS

    path = tmp_path / "agents" / "support" / "data" / tenant_id / str(agent_id) / "agent_state.db"
    db = SQLiteDatabase(path=path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _desired_state() -> DesiredState:
    return DesiredState(
        node_id="node-a",
        agents=[
            DesiredAgent(
                agent_id=101,
                name="support",
                config={"name": "support", "tenant_id": "tenant-1"},
                secrets={},
            )
        ],
    )


def _queue_text(db: SQLiteDatabase, *, dedup_key: str = "approval:a1:slack:U_LEAD") -> str:
    import fleetent.im_gateway.outbound_queue_store as store

    store.set_state_db(db)
    row = store.enqueue(
        platform="slack",
        address={"target": "U_LEAD", "target_type": "user"},
        payload={"kind": "text", "text": "approval needed"},
        dedup_key=dedup_key,
        created_at="2026-06-22T00:00:00+00:00",
    )
    return str(row["id"])


async def test_node_im_edge_drains_queue_and_marks_sent(tmp_path: Path, monkeypatch) -> None:
    from fleetent.node.im_edge import NodeIMEdgeHost
    from fleetent.outbound import DeliveryReceipt

    db = _agent_state_db(tmp_path)
    queue_id = _queue_text(db)

    host = NodeIMEdgeHost(_config(tmp_path))
    host.reconcile(_desired_state())
    monkeypatch.setattr(
        "fleetent.outbound.send_to",
        AsyncMock(
            return_value=DeliveryReceipt(
                ok=True,
                platform="slack",
                target="U_LEAD",
                target_type="user",
                kind="text",
            )
        ),
    )
    try:
        await host._drain_outbound_once()
    finally:
        host.close()

    row = db.execute(
        "SELECT status, sent_at FROM im_outbound_queue WHERE id = :id", {"id": queue_id}
    ).fetchone()
    assert row is not None
    assert row["status"] == "sent"
    assert row["sent_at"] is not None


async def test_node_im_edge_failed_send_increments_attempts_and_leaves_pending(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.node.im_edge import NodeIMEdgeHost
    from fleetent.outbound import DeliveryReceipt

    db = _agent_state_db(tmp_path)
    queue_id = _queue_text(db, dedup_key="approval:a2:slack:U_LEAD")

    host = NodeIMEdgeHost(_config(tmp_path))
    host.reconcile(_desired_state())
    monkeypatch.setattr(
        "fleetent.outbound.send_to",
        AsyncMock(
            return_value=DeliveryReceipt(
                ok=False,
                platform="slack",
                target="U_LEAD",
                target_type="user",
                kind="text",
                error="boom",
            )
        ),
    )
    try:
        await host._drain_outbound_once()
    finally:
        host.close()

    row = db.execute(
        "SELECT status, attempts, sent_at FROM im_outbound_queue WHERE id = :id",
        {"id": queue_id},
    ).fetchone()
    assert row is not None
    assert dict(row) == {"status": "pending", "attempts": 1, "sent_at": None}


async def test_node_im_edge_dedups_after_restart_before_mark_sent(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.node.im_edge import NodeIMEdgeHost
    from fleetent.outbound import DeliveryReceipt

    db = _agent_state_db(tmp_path)
    _queue_text(db, dedup_key="approval:a3:slack:U_LEAD")

    send_to = AsyncMock(
        return_value=DeliveryReceipt(
            ok=True,
            platform="slack",
            target="U_LEAD",
            target_type="user",
            kind="text",
        )
    )
    monkeypatch.setattr("fleetent.outbound.send_to", send_to)

    host1 = NodeIMEdgeHost(_config(tmp_path))
    host1.reconcile(_desired_state())
    original_mark_sent = host1._mark_queue_sent

    async def _crash_after_dedup(agent_name: str, row: dict[str, object]) -> None:
        raise RuntimeError("crash before mark_sent")

    monkeypatch.setattr(host1, "_mark_queue_sent", _crash_after_dedup)
    try:
        await host1._drain_outbound_once()
    finally:
        host1.close()

    host2 = NodeIMEdgeHost(_config(tmp_path))
    host2.reconcile(_desired_state())
    try:
        await host2._drain_outbound_once()
    finally:
        host2.close()

    assert send_to.await_count == 1
    rows = db.execute("SELECT status, sent_at FROM im_outbound_queue").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "sent"
    assert rows[0]["sent_at"] is not None


# ---------------------------------------------------------------------------
# Task 2.3 / 2.4 — drain user_id fan-out
# ---------------------------------------------------------------------------


def _queue_user_id_intent(
    db: SQLiteDatabase, user_id: str, *, dedup_key: str = "notify:user:1"
) -> str:
    import fleetent.im_gateway.outbound_queue_store as store

    store.set_state_db(db)
    row = store.enqueue(
        platform="directed",
        address={"target_type": "user_id", "user_id": user_id},
        payload={"kind": "text", "text": "please review"},
        dedup_key=dedup_key,
        created_at="2026-06-22T00:00:00+00:00",
    )
    return str(row["id"])


async def test_node_im_edge_drains_user_id_intent_fan_out(tmp_path: Path, monkeypatch) -> None:
    from fleetent.node.im_edge import NodeIMEdgeHost
    from fleetent.outbound import DeliveryReceipt

    db = _agent_state_db(tmp_path)
    queue_id = _queue_user_id_intent(db, "user-42")

    # Fake address resolver: user-42 has slack + telegram
    def _fake_resolve(user_id: str) -> list[dict[str, str]]:
        assert user_id == "user-42"
        return [
            {"platform": "slack", "platform_user_id": "U_alice"},
            {"platform": "telegram", "platform_user_id": "TG_alice"},
        ]

    send_to = AsyncMock(
        return_value=DeliveryReceipt(
            ok=True, platform="slack", target="U_alice", target_type="user", kind="text"
        )
    )
    monkeypatch.setattr("fleetent.outbound.send_to", send_to)

    host = NodeIMEdgeHost(_config(tmp_path))
    monkeypatch.setattr(host._address_resolver, "resolve", _fake_resolve)
    host.reconcile(_desired_state())
    try:
        await host._drain_outbound_once()
    finally:
        host.close()

    # fan-out: both channels received the message
    assert send_to.await_count == 2
    calls_platforms = {c.args[0] for c in send_to.await_args_list}
    assert calls_platforms == {"slack", "telegram"}

    row = db.execute(
        "SELECT status FROM im_outbound_queue WHERE id = :id", {"id": queue_id}
    ).fetchone()
    assert row["status"] == "sent"


async def test_node_im_edge_user_id_intent_no_bindings_skips_delivery(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.node.im_edge import NodeIMEdgeHost

    db = _agent_state_db(tmp_path)
    queue_id = _queue_user_id_intent(db, "user-ghost", dedup_key="notify:user:2")

    def _fake_resolve(user_id: str) -> list[dict[str, str]]:
        return []

    send_to = AsyncMock()
    monkeypatch.setattr("fleetent.outbound.send_to", send_to)

    host = NodeIMEdgeHost(_config(tmp_path))
    monkeypatch.setattr(host._address_resolver, "resolve", _fake_resolve)
    host.reconcile(_desired_state())
    try:
        await host._drain_outbound_once()
    finally:
        host.close()

    send_to.assert_not_called()
    # row still marked sent (no delivery needed but intent is consumed)
    row = db.execute(
        "SELECT status FROM im_outbound_queue WHERE id = :id", {"id": queue_id}
    ).fetchone()
    assert row["status"] == "sent"


async def test_node_im_edge_user_id_intent_single_channel_failure_continues(
    tmp_path: Path, monkeypatch
) -> None:
    """Single channel delivery failure must not stop fan-out to other channels."""
    from fleetent.node.im_edge import NodeIMEdgeHost
    from fleetent.outbound import DeliveryReceipt

    db = _agent_state_db(tmp_path)
    queue_id = _queue_user_id_intent(db, "user-42", dedup_key="notify:user:3")

    def _fake_resolve(user_id: str) -> list[dict[str, str]]:
        return [
            {"platform": "slack", "platform_user_id": "U_alice"},
            {"platform": "telegram", "platform_user_id": "TG_alice"},
        ]

    call_count = 0

    async def _failing_first_send(platform, connector, target, text, **kwargs):
        nonlocal call_count
        call_count += 1
        if platform == "slack":
            raise RuntimeError("slack connector unavailable")
        return DeliveryReceipt(
            ok=True, platform=platform, target=target, target_type="user", kind="text"
        )

    monkeypatch.setattr("fleetent.outbound.send_to", _failing_first_send)

    host = NodeIMEdgeHost(_config(tmp_path))
    monkeypatch.setattr(host._address_resolver, "resolve", _fake_resolve)
    host.reconcile(_desired_state())
    try:
        await host._drain_outbound_once()
    finally:
        host.close()

    # Both channels attempted (2 calls), telegram succeeded despite slack failure
    assert call_count == 2
    # Row still marked sent after bulkhead (partial delivery is acceptable)
    row = db.execute(
        "SELECT status FROM im_outbound_queue WHERE id = :id", {"id": queue_id}
    ).fetchone()
    assert row["status"] == "sent"
