"""Dev KB service key helper: keep <home>/.dev_kb_service_key and <home>/.env in sync.

The KB service key is the shared Bearer secret between kb-serve and its clients
(platform admin proxy, agent HTTP provider). kb-serve/kb-worker read it from
``<home>/.env`` (auto-loaded next to kb-service.yaml); the platform process gets
it via the Makefile's FLEETENT_KB_SERVICE_KEY export from the key file — this
script keeps both sides pointing at the same value.
"""

from __future__ import annotations

import secrets
from pathlib import Path

_ENV_KEY = "FLEETENT_KB_SERVICE_KEY"


def ensure_dev_kb_service_key(home: str | Path) -> str:
    """Return the dev KB service key, creating and syncing it if needed.

    Idempotent: the key persists in ``<home>/.dev_kb_service_key``; the
    ``FLEETENT_KB_SERVICE_KEY`` line in ``<home>/.env`` is upserted to match
    (the scaffolded template ships a ``replace-me`` placeholder).
    """
    home_dir = Path(home)
    key_file = home_dir / ".dev_kb_service_key"
    if key_file.exists():
        key = key_file.read_text().strip()
    else:
        key = secrets.token_hex(32)
        key_file.write_text(key)

    env_file = home_dir / ".env"
    line = f"{_ENV_KEY}={key}"
    if env_file.exists():
        lines = env_file.read_text().splitlines()
        for index, existing in enumerate(lines):
            if existing.startswith(f"{_ENV_KEY}="):
                if existing != line:
                    lines[index] = line
                    env_file.write_text("\n".join(lines) + "\n")
                break
        else:
            env_file.write_text("\n".join([*lines, line]) + "\n")
    else:
        env_file.write_text(line + "\n")
    return key


if __name__ == "__main__":
    import os

    home = os.environ.get("FLEETENT_HOME", os.path.join(os.getcwd(), ".fleetent-dev"))
    print(ensure_dev_kb_service_key(home))
