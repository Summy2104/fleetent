"""Connector credential resolution: DB config first, .env fallback, with masked reads."""

import json
from typing import Any, cast

from fleetent.platform.im_gateway_management import im_connector_store

# Credential keys per OWNER-LEVEL platform, and how they map to .env (config.Settings).
# Slack is intentionally absent: it is per-agent (per-agent-slack-connector), declared
# in agent.yaml `connectors.slack` with env-reference tokens, not an owner-level connector.
PLATFORM_CONFIG_KEYS: dict[str, list[str]] = {
    "telegram": ["bot_token"],
    "whatsapp": [
        "phone_number_id",
        "access_token",
        "verify_token",
        "business_account_id",
    ],
}

_ENV_MAP: dict[tuple[str, str], str] = {
    ("telegram", "bot_token"): "telegram_bot_token",
    ("whatsapp", "phone_number_id"): "whatsapp_phone_number_id",
    ("whatsapp", "access_token"): "whatsapp_access_token",
    ("whatsapp", "verify_token"): "whatsapp_verify_token",
    ("whatsapp", "business_account_id"): "whatsapp_business_account_id",
}


def get_settings() -> Any:
    """Return the app Settings. Wrapped so tests can monkeypatch the .env source."""
    from fleetent.config import Settings

    return Settings(anthropic_api_key="")


def resolve(owner_id: str, platform: str) -> dict[str, str]:
    """Resolve an owner's connector credentials: DB config if present, else admin-only env."""
    row = im_connector_store.get_connector(owner_id, platform)
    if row and row["config"]:
        return cast(dict[str, str], json.loads(row["config"]))
    if _is_admin_owner(owner_id):
        return _env_fallback(platform)
    return {}


def resolve_masked(owner_id: str, platform: str) -> dict[str, str]:
    """Like resolve() but with credential values masked to the last 4 characters."""
    return {k: _mask(v) for k, v in resolve(owner_id, platform).items()}


def set_config(owner_id: str, platform: str, config: dict[str, str]) -> None:
    """Persist connector config to the DB (marks the connector for reload on next start)."""
    im_connector_store.upsert_connector(owner_id, platform, config=json.dumps(config))


def seed_from_env(force: bool = False) -> list[str]:
    """Populate the admin owner's connector configs from .env once.

    Returns platforms that got credentials. Only the built-in admin owner inherits .env.
    """
    from fleetent import user_store

    owner_id = user_store.admin_owner_id()
    seeded: list[str] = []
    for platform in PLATFORM_CONFIG_KEYS:
        existing = im_connector_store.get_connector(owner_id, platform)
        if existing and existing["config"] and not force:
            continue
        cfg = _env_fallback(platform)
        if cfg:
            im_connector_store.upsert_connector(
                owner_id, platform, config=json.dumps(cfg), enabled=True
            )
            seeded.append(platform)
        else:
            im_connector_store.upsert_connector(owner_id, platform, status="unconfigured")
    return seeded


def _is_admin_owner(owner_id: str) -> bool:
    from fleetent import user_store

    return owner_id == user_store.admin_owner_id()


def _env_fallback(platform: str) -> dict[str, str]:
    settings = get_settings()
    out: dict[str, str] = {}
    for key in PLATFORM_CONFIG_KEYS.get(platform, []):
        env_attr = _ENV_MAP.get((platform, key))
        value = getattr(settings, env_attr, "") if env_attr else ""
        if value:
            out[key] = value
    return out


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]
