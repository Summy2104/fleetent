from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when fleetent node start configuration is missing or invalid."""


@dataclass(frozen=True)
class NodeConfig:
    platform_url: str
    node_id: str
    service_key: str
    home_dir: Path
    interval_seconds: int = 10
    advertise_host: str | None = None


def load_config() -> NodeConfig:
    """Load fleetent node start config from environment variables."""
    home_dir = Path(os.environ.get("FLEETENT_HOME") or Path.home() / ".fleetent").expanduser()
    env_path = home_dir / "node" / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)

    platform_url = _require_env("FLEETENT_NODE_PLATFORM_URL")
    node_id = _require_env("FLEETENT_NODE_ID")
    service_key = _require_env("FLEETENT_NODE_SERVICE_KEY")
    interval_seconds = int(os.environ.get("FLEETENT_NODE_INTERVAL_SECONDS", "10"))
    advertise_host = os.environ.get("FLEETENT_NODE_ADVERTISE_HOST", "").strip() or None
    return NodeConfig(
        platform_url=platform_url.rstrip("/"),
        node_id=node_id,
        service_key=service_key,
        home_dir=home_dir,
        interval_seconds=interval_seconds,
        advertise_host=advertise_host,
    )


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"missing required environment variable: {name}")
    return value
