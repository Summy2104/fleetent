"""Integration tests for POST /webhook/{source_id} endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from starlette.testclient import TestClient

import mini_agent.server as srv
import mini_agent.webhook_router as wr


def _make_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _yaml_with_source(tmp_path, source_id="test-src", secret=None, user_id="u-1",
                       agent_name=None, message_template=None) -> object:
    """Write a webhooks.yaml with one source and return the path."""
    entry: dict = {"id": source_id, "user_id": user_id}
    if secret:
        entry["secret"] = secret
    if agent_name:
        entry["agent_name"] = agent_name
    if message_template:
        entry["message_template"] = message_template
    p = tmp_path / "webhooks.yaml"
    p.write_text(yaml.dump({"sources": [entry]}))
    return p


# ── 202 / 404 / 403 ──────────────────────────────────────────────────────────


def test_webhook_known_source_returns_202(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH", _yaml_with_source(tmp_path))

    with patch("mini_agent.im_gateway.normalizer.route", new=AsyncMock()):
        with TestClient(srv.app) as client:
            resp = client.post("/webhook/test-src", json={"event": "push"})

    assert resp.status_code == 202


def test_webhook_unknown_source_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH", _yaml_with_source(tmp_path))

    with TestClient(srv.app) as client:
        resp = client.post("/webhook/unknown-src", json={})

    assert resp.status_code == 404


def test_webhook_invalid_signature_returns_403(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH",
                        _yaml_with_source(tmp_path, secret="mysecret"))

    with TestClient(srv.app) as client:
        resp = client.post(
            "/webhook/test-src",
            json={"event": "push"},
            headers={"x-hub-signature-256": "sha256=badhex"},
        )

    assert resp.status_code == 403


def test_webhook_missing_signature_returns_403(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH",
                        _yaml_with_source(tmp_path, secret="mysecret"))

    with TestClient(srv.app) as client:
        resp = client.post("/webhook/test-src", json={"event": "push"})

    assert resp.status_code == 403


def test_webhook_valid_signature_returns_202(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH",
                        _yaml_with_source(tmp_path, secret="mysecret"))

    body = json.dumps({"event": "push"}).encode()
    sig = _make_sig("mysecret", body)

    with patch("mini_agent.im_gateway.normalizer.route", new=AsyncMock()):
        with TestClient(srv.app) as client:
            resp = client.post(
                "/webhook/test-src",
                content=body,
                headers={"content-type": "application/json",
                         "x-hub-signature-256": sig},
            )

    assert resp.status_code == 202


def test_webhook_no_secret_accepts_without_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_WEBHOOK_YAML_PATH",
                        _yaml_with_source(tmp_path, secret=None))

    with patch("mini_agent.im_gateway.normalizer.route", new=AsyncMock()):
        with TestClient(srv.app) as client:
            resp = client.post("/webhook/test-src", json={"event": "push"})

    assert resp.status_code == 202


# ── background task dispatch ──────────────────────────────────────────────────


async def test_webhook_dispatches_normalized_message(monkeypatch):
    import asyncio
    from httpx import ASGITransport, AsyncClient

    # Directly populate sources — AsyncClient doesn't trigger lifespan
    source = wr.WebhookSource(id="test-src", user_id="webhook-user",
                               message_template="event: {event}")
    monkeypatch.setitem(srv._webhook_sources, "test-src", source)

    route_mock = AsyncMock()
    with patch("mini_agent.im_gateway.normalizer.route", new=route_mock):
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
    with patch("mini_agent.im_gateway.normalizer.route", new=route_mock):
        async with AsyncClient(
            transport=ASGITransport(app=srv.app), base_url="http://test"
        ) as client:
            await client.post("/webhook/test-src", json={})
        await asyncio.sleep(0)

    msg = route_mock.call_args[0][0]
    await msg.reply_func("some reply")  # must not raise
