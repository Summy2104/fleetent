"""Integration tests for POST /webhook/{source_id} endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

import fleetent.server as srv
import fleetent.webhook_router as wr
from fleetent.config import WebhooksSettings


@pytest.fixture(autouse=True)
def isolate_runtime_config_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _make_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _source(
    source_id="test-src",
    secret=None,
    user_id="u-1",
    agent_name=None,
    message_template=None,
) -> wr.WebhookSource:
    return wr.WebhookSource(
        id=source_id,
        user_id=user_id,
        secret=secret,
        agent_name=agent_name,
        message_template=message_template,
    )


# ── 202 / 404 / 403 ──────────────────────────────────────────────────────────


def test_webhook_known_source_returns_202(tmp_path, monkeypatch, isolated_schedule_db):
    srv._webhook_sources.clear()

    with (
        patch("fleetent.im_gateway.normalizer.route", new=AsyncMock()),
        TestClient(srv.app) as client,
    ):
        monkeypatch.setitem(srv._webhook_sources, "test-src", _source())
        resp = client.post("/webhook/test-src", json={"event": "push"})

    assert resp.status_code == 202


def test_webhook_unknown_source_returns_404(tmp_path, monkeypatch, isolated_schedule_db):
    srv._webhook_sources.clear()

    with TestClient(srv.app) as client:
        resp = client.post("/webhook/unknown-src", json={})

    assert resp.status_code == 404


def test_webhook_invalid_signature_returns_403(tmp_path, monkeypatch, isolated_schedule_db):
    srv._webhook_sources.clear()

    with TestClient(srv.app) as client:
        monkeypatch.setitem(srv._webhook_sources, "test-src", _source(secret="mysecret"))
        resp = client.post(
            "/webhook/test-src",
            json={"event": "push"},
            headers={"x-hub-signature-256": "sha256=badhex"},
        )

    assert resp.status_code == 403


def test_webhook_missing_signature_returns_403(tmp_path, monkeypatch, isolated_schedule_db):
    srv._webhook_sources.clear()

    with TestClient(srv.app) as client:
        monkeypatch.setitem(srv._webhook_sources, "test-src", _source(secret="mysecret"))
        resp = client.post("/webhook/test-src", json={"event": "push"})

    assert resp.status_code == 403


def test_webhook_valid_signature_returns_202(tmp_path, monkeypatch, isolated_schedule_db):
    srv._webhook_sources.clear()

    body = json.dumps({"event": "push"}).encode()
    sig = _make_sig("mysecret", body)

    with (
        patch("fleetent.im_gateway.normalizer.route", new=AsyncMock()),
        TestClient(srv.app) as client,
    ):
        monkeypatch.setitem(srv._webhook_sources, "test-src", _source(secret="mysecret"))
        resp = client.post(
            "/webhook/test-src",
            content=body,
            headers={"content-type": "application/json", "x-hub-signature-256": sig},
        )

    assert resp.status_code == 202


def test_webhook_no_secret_accepts_without_signature(tmp_path, monkeypatch, isolated_schedule_db):
    srv._webhook_sources.clear()

    with (
        patch("fleetent.im_gateway.normalizer.route", new=AsyncMock()),
        TestClient(srv.app) as client,
    ):
        monkeypatch.setitem(srv._webhook_sources, "test-src", _source(secret=None))
        resp = client.post("/webhook/test-src", json={"event": "push"})

    assert resp.status_code == 202


# NOTE: main fail-fast-rejected a legacy config/webhooks.yaml (yaml→runtime-API
# design). The merge kept zhangyang's yaml source loading, so that fail-fast test was
# removed. The gating tests below (disabled / max-body) enforce the security model.


def test_webhooks_disabled_rejects_before_dispatch(monkeypatch):
    srv._webhook_sources.clear()
    monkeypatch.setitem(srv._webhook_sources, "test-src", _source())
    monkeypatch.setattr(srv.app.state, "webhook_settings", WebhooksSettings(enabled=False))
    route_mock = AsyncMock()

    with patch("fleetent.im_gateway.normalizer.route", new=route_mock):
        resp = TestClient(srv.app).post("/webhook/test-src", json={"event": "push"})

    assert resp.status_code == 503
    route_mock.assert_not_called()


def test_webhook_max_body_size_rejects_before_dispatch(monkeypatch):
    srv._webhook_sources.clear()
    monkeypatch.setitem(srv._webhook_sources, "test-src", _source())
    monkeypatch.setattr(srv.app.state, "webhook_settings", WebhooksSettings(max_body_bytes=5))
    route_mock = AsyncMock()

    with patch("fleetent.im_gateway.normalizer.route", new=route_mock):
        resp = TestClient(srv.app).post(
            "/webhook/test-src",
            content=b'{"event":"push"}',
            headers={"content-type": "application/json"},
        )

    assert resp.status_code == 413
    route_mock.assert_not_called()


# ── background task dispatch ──────────────────────────────────────────────────


async def test_webhook_dispatches_normalized_message(monkeypatch):
    import asyncio

    from httpx import ASGITransport, AsyncClient

    # Directly populate sources — AsyncClient doesn't trigger lifespan
    source = wr.WebhookSource(
        id="test-src", user_id="webhook-user", message_template="event: {event}"
    )
    monkeypatch.setitem(srv._webhook_sources, "test-src", source)

    route_mock = AsyncMock()
    with patch("fleetent.im_gateway.normalizer.route", new=route_mock):
        async with AsyncClient(
            transport=ASGITransport(app=srv.app), base_url="http://test"
        ) as client:
            resp = await client.post("/webhook/test-src", json={"event": "push"})
        await asyncio.sleep(0)

    assert resp.status_code == 202
    route_mock.assert_called_once()
    msg = route_mock.call_args[0][0]
    assert msg.platform == "webhook"
    assert msg.session_id == "webhook-test-src"
    assert msg.user_id == "webhook-user"
    assert msg.text == "event: push"


async def test_webhook_reply_func_is_noop(monkeypatch):
    import asyncio

    from httpx import ASGITransport, AsyncClient

    source = wr.WebhookSource(id="test-src", user_id="u-1")
    monkeypatch.setitem(srv._webhook_sources, "test-src", source)

    route_mock = AsyncMock()
    with patch("fleetent.im_gateway.normalizer.route", new=route_mock):
        async with AsyncClient(
            transport=ASGITransport(app=srv.app), base_url="http://test"
        ) as client:
            await client.post("/webhook/test-src", json={})
        await asyncio.sleep(0)

    msg = route_mock.call_args[0][0]
    await msg.reply_func("some reply")  # must not raise
