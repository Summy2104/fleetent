from datetime import UTC, datetime, timedelta

from fleetent.platform.im_gateway_management.pending_link_store import PendingLinkStore


def test_pop_valid_returns_entry_once_before_expiry() -> None:
    store = PendingLinkStore(ttl=timedelta(minutes=10))
    now = datetime(2026, 6, 22, tzinfo=UTC)

    store.put("code-1", user_id="user-1", tenant_id="tenant-1", now=now)

    entry = store.pop_valid("code-1", now=now + timedelta(minutes=1))

    assert entry is not None
    assert entry.user_id == "user-1"
    assert entry.tenant_id == "tenant-1"
    assert store.pop_valid("code-1", now=now + timedelta(minutes=1)) is None


def test_pop_valid_rejects_expired_codes() -> None:
    store = PendingLinkStore(ttl=timedelta(minutes=10))
    now = datetime(2026, 6, 22, tzinfo=UTC)

    store.put("code-2", user_id="user-2", tenant_id="tenant-2", now=now)

    assert store.pop_valid("code-2", now=now + timedelta(minutes=11)) is None
