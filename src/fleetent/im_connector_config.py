"""Connector credential resolution: DB config first, .env fallback, with masked reads."""

import json
from typing import Any, cast

from fleetent import im_connector_store

# Credential keys per platform, and how they map to .env (config.Settings) fields.
PLATFORM_CONFIG_KEYS: dict[str, list[str]] = {
    "slack": ["bot_token", "app_token"],
    "telegram": ["bot_token"],
    "whatsapp": [],
}

_ENV_MAP: dict[tuple[str, str], str] = {
    ("slack", "bot_token"): "slack_bot_token",
    ("slack", "app_token"): "slack_app_token",
    ("telegram", "bot_token"): "telegram_bot_token",
}


def get_settings() -> Any:
    """Return the app Settings. Wrapped so tests can monkeypatch the .env source."""
    from fleetent.config import Settings

    return Settings(anthropic_api_key="")


def resolve(platform: str) -> dict[str, str]:
    """Resolve a connector's credentials: DB config if present, else .env fallback."""
    row = im_connector_store.get_connector(platform)
    if row and row["config"]:
        return cast(dict[str, str], json.loads(row["config"]))
    return _env_fallback(platform)


def resolve_masked(platform: str) -> dict[str, str]:
    """Like resolve() but with credential values masked to the last 4 characters."""
    return {k: _mask(v) for k, v in resolve(platform).items()}


def set_config(platform: str, config: dict[str, str]) -> None:
    """Persist connector config to the DB (marks the connector for reload on next start)."""
    im_connector_store.upsert_connector(platform, config=json.dumps(config))


def seed_from_env(force: bool = False) -> list[str]:
    """Populate connector configs from .env once. Returns platforms that got credentials."""
    seeded: list[str] = []
    for platform in PLATFORM_CONFIG_KEYS:
        existing = im_connector_store.get_connector(platform)
        if existing and existing["config"] and not force:
            continue
        cfg = _env_fallback(platform)
        if cfg:
            im_connector_store.upsert_connector(platform, config=json.dumps(cfg), enabled=True)
            seeded.append(platform)
        else:
            im_connector_store.upsert_connector(platform, status="unconfigured")
    return seeded


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
