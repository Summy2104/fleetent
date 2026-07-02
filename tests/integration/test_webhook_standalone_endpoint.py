"""Integration: standalone agent_app POST /webhook/{source_id} (live-webhooks).

Standalone agent (``fleetent agent run``) exposes an inbound webhook endpoint that, for a
source declared in ``agent.yaml`` (``webhooks.sources``), verifies HMAC, builds a
``NormalizedMessage`` (run as the source's ``user_id``, ``session_id="webhook-{id}"``), and
schedules ``normalizer.route()`` in the background while returning 202 immediately.

No platform, no management DB — the source comes from the in-memory agent index only.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.config import WebhookSourceSettings, WebhooksSettings
from fleetent.im_gateway import normalizer
from fleetent.runtime import agent_app


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _install_agent(monkeypatch, *, sources, enabled=True, max_body_bytes=1_048_576):
    agent = AgentFile(
        name="test-agent",
        version=1,
        models=default_models(),
        webhooks=WebhooksSettings(enabled=enabled, max_body_bytes=max_body_bytes, sources=sources),
    )
    index = AgentConfigIndex(agents={"test-agent": agent}, default="test-agent")
    monkeypatch.setattr(agent_config, "_index", index)
    return agent


def _client(monkeypatch):
    captured: list[normalizer.NormalizedMessage] = []

    async def _fake_route(msg, principal=None):
        captured.append(msg)

    monkeypatch.setattr(normalizer, "route", _fake_route)
    app = agent_app.build_app("test-agent")
    return TestClient(app, raise_server_exceptions=True), captured


def test_unknown_source_returns_404(monkeypatch):
    _install_agent(monkeypatch, sources=[])
    client, captured = _client(monkeypatch)
    resp = client.post("/webhook/nope", json={"event": "push"})
    assert resp.status_code == 404
    assert captured == []


def test_known_source_no_secret_returns_202_and_routes(monkeypatch):
    _install_agent(
        monkeypatch,
        sources=[
            WebhookSourceSettings(
                id="github-ci",
                user_id="u-internal-1",
                message_template="pushed to {ref}",
            )
        ],
    )
    client, captured = _client(monkeypatch)
    resp = client.post("/webhook/github-ci", json={"ref": "main"})
    assert resp.status_code == 202
    assert len(captured) == 1
    msg = captured[0]
    assert msg.platform == "webhook"
    assert msg.session_id == "webhook-github-ci"
    assert msg.user_id == "u-internal-1"
    assert msg.text == "pushed to main"


def test_hmac_failure_returns_403_and_no_route(monkeypatch):
    monkeypatch.setenv("HOOK_SECRET", "s3cr3t")
    _install_agent(
        monkeypatch,
        sources=[WebhookSourceSettings(id="gh", user_id="u1", secret_env="HOOK_SECRET")],
    )
    client, captured = _client(monkeypatch)
    resp = client.post(
        "/webhook/gh",
        content=json.dumps({"x": 1}),
        headers={"X-Hub-Signature-256": "sha256=bad", "Content-Type": "application/json"},
    )
    assert resp.status_code == 403
    assert captured == []


def test_hmac_success_returns_202(monkeypatch):
    monkeypatch.setenv("HOOK_SECRET", "s3cr3t")
    _install_agent(
        monkeypatch,
        sources=[WebhookSourceSettings(id="gh", user_id="u1", secret_env="HOOK_SECRET")],
    )
    client, captured = _client(monkeypatch)
    body = json.dumps({"x": 1}).encode()
    resp = client.post(
        "/webhook/gh",
        content=body,
        headers={
            "X-Hub-Signature-256": _sig("s3cr3t", body),
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    assert len(captured) == 1


def test_webhooks_disabled_returns_403(monkeypatch):
    _install_agent(
        monkeypatch,
        enabled=False,
        sources=[WebhookSourceSettings(id="gh", user_id="u1")],
    )
    client, captured = _client(monkeypatch)
    resp = client.post("/webhook/gh", json={"x": 1})
    assert resp.status_code == 403
    assert captured == []


def test_body_too_large_returns_413(monkeypatch):
    _install_agent(
        monkeypatch,
        max_body_bytes=10,
        sources=[WebhookSourceSettings(id="gh", user_id="u1")],
    )
    client, captured = _client(monkeypatch)
    resp = client.post("/webhook/gh", json={"x": "a" * 100})
    assert resp.status_code == 413
    assert captured == []


def test_reply_is_noop_when_no_reply_target(monkeypatch):
    """Default (no reply_target): reply_func must not call directed-reach outbound."""
    import anyio

    from fleetent import outbound_connectors

    calls: list = []

    async def _notify(*a, **k):
        calls.append((a, k))

    monkeypatch.setattr(outbound_connectors, "notify_user", _notify)
    _install_agent(monkeypatch, sources=[WebhookSourceSettings(id="gh", user_id="u1")])
    client, captured = _client(monkeypatch)
    resp = client.post("/webhook/gh", json={"x": 1})
    assert resp.status_code == 202
    anyio.run(captured[0].reply_func, "some result")
    assert calls == []


def test_reply_target_delivers_via_notify_user(monkeypatch):
    """reply_target set → reply_func delivers the run result via directed-reach notify_user."""
    import anyio

    from fleetent import outbound_connectors

    calls: list = []

    async def _notify(*a, **k):
        calls.append((a, k))

    monkeypatch.setattr(outbound_connectors, "notify_user", _notify)
    _install_agent(
        monkeypatch,
        sources=[WebhookSourceSettings(id="gh", user_id="u1", reply_target="u-internal-9")],
    )
    client, captured = _client(monkeypatch)
    resp = client.post("/webhook/gh", json={"x": 1})
    assert resp.status_code == 202
    anyio.run(captured[0].reply_func, "the run result")
    assert len(calls) == 1
    assert calls[0][0][0] == "u-internal-9"
    assert calls[0][0][1] == "the run result"


def test_managed_trusted_source_header_skips_hmac_and_uses_header(monkeypatch):
    """Managed: a trusted X-Fleetent-Webhook-Source header (from node) supplies the source.

    No agent.yaml entry, no HMAC — the platform already verified. The header carries
    user_id / template / reply_target, and the run routes as that user.
    """
    import json as _json

    _install_agent(monkeypatch, sources=[])  # nothing in agent.yaml
    client, captured = _client(monkeypatch)
    resp = client.post(
        "/webhook/remote-src",
        json={"ref": "main"},
        headers={
            "X-Fleetent-Webhook-Source": _json.dumps(
                {
                    "user_id": "u-managed",
                    "agent_name": "test-agent",
                    "message_template": "pushed {ref}",
                    "reply_target": "u-internal-9",
                }
            )
        },
    )
    assert resp.status_code == 202
    assert len(captured) == 1
    assert captured[0].user_id == "u-managed"
    assert captured[0].text == "pushed main"
    assert captured[0].session_id == "webhook-remote-src"
