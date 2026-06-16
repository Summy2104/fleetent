"""Platform fire-time creator recheck injected into cron_scheduler.

The platform closure `server._cron_principal_recheck` performs the users-table
revocation recheck that the agent-side scheduler delegates to it in platform mode
(decouple-cron-principal-recheck). Lives in integration because it imports
`fleetent.server`, which pulls in `fleetent.platform.*`.
"""

from __future__ import annotations


def _make_user(uid: str, status: str = "active", tenant_id: str = "default"):
    from fleetent import user_store

    return user_store.User(
        id=uid, name="Test", created_at="2024-01-01", status=status, tenant_id=tenant_id
    )


def _im_origin() -> dict:
    return {"platform": "slack", "chat_id": "D0"}


def test_recheck_rejects_blocked_creator(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.server import _cron_principal_recheck

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid, status="blocked"))
    assert _cron_principal_recheck({"id": "t", "user_id": "u1", "origin": _im_origin()}) is None


def test_recheck_returns_current_principal_for_active_creator(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.identity import Principal
    from fleetent.server import _cron_principal_recheck

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid, tenant_id="acme"))
    assert _cron_principal_recheck({"id": "t", "user_id": "u2", "origin": None}) == Principal(
        user_id="u2", tenant_id="acme"
    )


def test_recheck_trusts_vanished_creator_with_im_origin(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.identity import Principal
    from fleetent.server import _cron_principal_recheck

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: None)
    assert _cron_principal_recheck(
        {"id": "t", "user_id": "u3", "origin": _im_origin()}
    ) == Principal(user_id="u3", tenant_id="default")


def test_recheck_rejects_vanished_creator_without_origin(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.server import _cron_principal_recheck

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: None)
    assert _cron_principal_recheck({"id": "t", "user_id": "u4", "origin": None}) is None
