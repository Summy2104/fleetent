"""Unit: standalone webhook source parsing from agent.yaml WebhooksSettings (live-webhooks).

Pure config parsing + env-ref secret resolution — no DB / endpoint. The standalone face reads
``agent.yaml``'s ``webhooks.sources`` and resolves each into a neutral ``WebhookSource``.
"""

from __future__ import annotations

from fleetent.config import WebhooksSettings
from fleetent.webhook_router import WebhookSource, sources_from_settings


def test_parses_sources_and_resolves_secret_env(monkeypatch):
    monkeypatch.setenv("GH_HOOK_SECRET", "s3cr3t")
    ws = WebhooksSettings.model_validate(
        {
            "enabled": True,
            "sources": [
                {
                    "id": "github-ci",
                    "user_id": "u1",
                    "agent_name": "bot",
                    "message_template": "PR: {repository[name]}",
                    "reply_target": "u-internal-9",
                    "secret_env": "GH_HOOK_SECRET",
                }
            ],
        }
    )
    sources = sources_from_settings(ws.sources)
    assert set(sources) == {"github-ci"}
    src = sources["github-ci"]
    assert isinstance(src, WebhookSource)
    assert src.user_id == "u1"
    assert src.agent_name == "bot"
    assert src.message_template == "PR: {repository[name]}"
    assert src.reply_target == "u-internal-9"
    assert src.secret == "s3cr3t"  # resolved from env, not the env name


def test_no_sources_is_empty():
    ws = WebhooksSettings.model_validate({"enabled": True})
    assert sources_from_settings(ws.sources) == {}


def test_secret_env_unset_resolves_to_none(monkeypatch):
    monkeypatch.delenv("MISSING_HOOK_SECRET", raising=False)
    ws = WebhooksSettings.model_validate(
        {"sources": [{"id": "x", "user_id": "u1", "secret_env": "MISSING_HOOK_SECRET"}]}
    )
    # unresolved env -> no secret (HMAC verification then open per verify_signature)
    assert sources_from_settings(ws.sources)["x"].secret is None
