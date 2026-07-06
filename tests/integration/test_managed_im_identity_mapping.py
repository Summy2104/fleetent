from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.integration._migration_template import apply_migrations


def _publish_agent(monkeypatch, *, name: str = "support", tenant_id: str = "default") -> None:
    from fleetent import agent_config
    from fleetent.agent_config import (
        AgentConfigIndex,
        AgentFile,
        ImBinding,
        TelegramBinding,
    )

    agent = AgentFile(
        name=name,
        version=1,
        tenant_id=tenant_id,
        models=agent_config.default_models(),
        im=ImBinding(telegram=TelegramBinding(bot_token_env="BOT")),
    )
    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(agents={name: agent}, default=name),
    )


def _capture_telegram_handler(agent_name: str):
    import fleetent.im_gateway.telegram as telegram

    captured: dict[str, object] = {}

    class FakeApp:
        def add_handler(self, handler):
            # First registration is the inbound MessageHandler (CallbackQueryHandler follows).
            captured.setdefault("handler", handler)

    class FakeBuilder:
        def token(self, _token):
            return self

        def concurrent_updates(self, _value):
            return self

        def build(self):
            return FakeApp()

    with patch("telegram.ext.Application") as app_cls:
        app_cls.builder.return_value = FakeBuilder()
        telegram.create_app(agent_name, {"bot_token": "test-token"})

    return captured["handler"].callback


def _make_update(user_id: int, text: str = "hi") -> MagicMock:
    message = MagicMock()
    message.caption = None
    message.text = text
    message.reply_to_message = None
    message.chat.type = "private"
    message.chat.id = 999
    message.photo = None
    message.document = None

    update = MagicMock()
    update.message = message
    update.effective_user.id = user_id
    update.effective_user.full_name = "Alice"
    return update


async def test_lifespan_maps_im_identity_to_internal_user_and_reuses_it(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    _publish_agent(monkeypatch, tenant_id="default")

    import fleetent.server as srv
    from fleetent.platform.im_gateway_management import identity as im_identity

    routed = []

    async def fake_route(msg):
        routed.append(msg)

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )

    with TestClient(srv.app):
        handler = _capture_telegram_handler("support")
        update = _make_update(424242)
        with patch("telegram.Update", MagicMock):
            await handler(update, MagicMock())
            await handler(update, MagicMock())

    assert [msg.user_id for msg in routed] == [routed[0].user_id, routed[0].user_id]
    assert routed[0].user_id != "424242"
    rows = im_identity.list_all()
    assert len(rows) == 1
    assert rows[0]["platform"] == "telegram"
    assert rows[0]["platform_user_id"] == "424242"
    assert rows[0]["user_id"] == routed[0].user_id


async def test_im_first_then_bearer_resolves_same_user_id(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    _publish_agent(monkeypatch, tenant_id="default")

    import fleetent.server as srv
    import fleetent.user_store as user_store

    routed = []

    async def fake_route(msg):
        routed.append(msg)

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )

    import fleetent.platform.user_management.api_key_store as aks

    with TestClient(srv.app):
        handler = _capture_telegram_handler("support")
        with patch("telegram.Update", MagicMock):
            await handler(_make_update(424242), MagicMock())

        user = user_store.get_by_id(routed[0].user_id)
        assert user is not None
        plaintext, _ = aks.issue_key(user.id)
        authenticated = user_store.authenticate(plaintext)

    assert authenticated is not None
    assert authenticated[0].id == routed[0].user_id


async def test_tenant_mismatch_rejects_im_message_with_diagnostic_log(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    _publish_agent(monkeypatch, tenant_id="tenant-a")

    import fleetent.server as srv
    from fleetent.platform.im_gateway_management import identity as im_identity
    from fleetent.platform.tenancy import store as tenancy_store

    tenancy_store.create_tenant(id="tenant-a", name="Tenant A")
    tenancy_store.create_tenant(id="tenant-b", name="Tenant B")

    user = im_identity.get_or_create("telegram", "424242", "default")
    tenancy_store.set_user_tenant(user.id, "tenant-b")

    routed = []

    async def fake_route(msg):
        routed.append(msg)

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )
    caplog.set_level(logging.WARNING)

    with TestClient(srv.app):
        handler = _capture_telegram_handler("support")
        with patch("telegram.Update", MagicMock):
            await handler(_make_update(424242), MagicMock())

    assert routed == []
    assert "tenant" in caplog.text.lower()


def test_resolver_rejects_blocked_managed_im_user(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    _publish_agent(monkeypatch, tenant_id="default")

    import fleetent.server as srv
    import fleetent.user_store as user_store
    from fleetent.im_gateway.access import IMIdentityResolutionError
    from fleetent.platform.im_gateway_management import identity as im_identity

    user = im_identity.get_or_create("telegram", "424242", "default")
    user_store.set_status(user.id, "blocked")

    with pytest.raises(IMIdentityResolutionError):
        srv._resolve_im_identity("support", "telegram", "424242")


async def test_non_default_tenant_new_im_user_routes_without_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    _publish_agent(monkeypatch, tenant_id="tenant-a")

    import fleetent.server as srv
    from fleetent.platform.tenancy import store as tenancy_store

    tenancy_store.create_tenant(id="tenant-a", name="Tenant A")

    routed = []

    async def fake_route(msg):
        routed.append(msg)

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )

    with TestClient(srv.app):
        handler = _capture_telegram_handler("support")
        with patch("telegram.Update", MagicMock):
            await handler(_make_update(424242), MagicMock())

    assert len(routed) == 1
    assert routed[0].user_id != "424242"


async def test_blocked_managed_im_user_is_rechecked_and_skipped_by_cron(
    tmp_path, monkeypatch, isolated_schedule_db
):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    _publish_agent(monkeypatch, tenant_id="default")

    import fleetent.cron_scheduler as cron_scheduler
    import fleetent.server as srv
    import fleetent.user_store as user_store
    from fleetent.session import manager as session_mgr

    routed = []

    async def fake_route(msg):
        routed.append(msg)

    async def fake_agent_run(*args, **kwargs):
        raise AssertionError("blocked managed IM user must not reach agent run")

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )
    monkeypatch.setattr(cron_scheduler, "_agent_run", fake_agent_run)
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    with TestClient(srv.app):
        handler = _capture_telegram_handler("support")
        with patch("telegram.Update", MagicMock):
            await handler(_make_update(424242), MagicMock())

    user_id = routed[0].user_id
    user_store.set_status(user_id, "blocked")

    await cron_scheduler._fire(
        {
            "id": "managed-im-task",
            "user_id": user_id,
            "message": "ping",
            "session_id": None,
            "agent_name": "support",
            "deliver": None,
            "origin": {"platform": "telegram", "chat_id": "999"},
        }
    )
