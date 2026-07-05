from __future__ import annotations

import os
from pathlib import Path

KB_SERVICE_KEY_ENV = "FLEETENT_KB_SERVICE_KEY"


def resolve_service_key_ref(auth_ref: str) -> str:
    if auth_ref.startswith("env:"):
        env_name = auth_ref.removeprefix("env:")
        value = os.getenv(env_name)
        if value:
            return value
        raise ValueError(f"kb service key env var is missing: {env_name}")
    path = Path(auth_ref.removeprefix("file://")).expanduser()
    return path.read_text(encoding="utf-8")
