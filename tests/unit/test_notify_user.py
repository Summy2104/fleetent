"""Unit tests for notify_user directed-reach agent-side primitive."""

from __future__ import annotations

import pytest


def _enable_node_managed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_ID", "node-a")
    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", "https://platform.internal")
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-" + "1" * 64)


def _disable_node_managed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLEETENT_NODE_ID", raising=False)
    monkeypatch.delenv("FLEETENT_NODE_PLATFORM_URL", raising=False)
    monkeypatch.delenv("FLEETENT_NODE_SERVICE_KEY", raising=False)


# ---------------------------------------------------------------------------
# Task 3.1 — managed runtime enqueues user_id intent
# ---------------------------------------------------------------------------


def test_notify_user_managed_enqueues_user_id_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.outbound_connectors import notify_user

    _enable_node_managed_env(monkeypatch)

    queued: list[dict] = []
    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: queued.append(kwargs) or {"id": "q1"},
    )

    notify_user("user-42", "Please approve this proposal.")

    assert len(queued) == 1
    q = queued[0]
    assert q["platform"] == "directed"
    assert q["address"]["target_type"] == "user_id"
    assert q["address"]["user_id"] == "user-42"
    assert q["payload"]["text"] == "Please approve this proposal."
    assert q["payload"]["kind"] == "text"


def test_notify_user_managed_enqueues_with_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.outbound_connectors import notify_user

    _enable_node_managed_env(monkeypatch)

    queued: list[dict] = []
    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: queued.append(kwargs) or {"id": "q1"},
    )

    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}]
    notify_user("user-42", "hi", blocks=blocks)

    assert queued[0]["payload"]["blocks"] == blocks


def test_notify_user_managed_does_not_query_im_users(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent side must never touch im_users — only node does the reverse lookup."""
    from fleetent.outbound_connectors import notify_user

    _enable_node_managed_env(monkeypatch)

    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: {"id": "q1"},
    )

    # If notify_user ever tried to import or call platform code, the module boundary
    # guardrail would catch it, but we also check it raises no AttributeError here.
    notify_user("user-42", "test")  # must not raise


# ---------------------------------------------------------------------------
# Task 3.2 — non-managed runtime is a no-op
# ---------------------------------------------------------------------------


def test_notify_user_non_managed_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.outbound_connectors import notify_user

    _disable_node_managed_env(monkeypatch)

    enqueue_calls: list = []
    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: enqueue_calls.append(kwargs),
    )

    notify_user("user-42", "this should be dropped")

    assert enqueue_calls == []


def test_notify_user_non_managed_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.outbound_connectors import notify_user

    _disable_node_managed_env(monkeypatch)

    # Must be a clean no-op — no exceptions
    notify_user("user-42", "test")
