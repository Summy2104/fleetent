"""Dev master key helper: idempotently ensure a Fernet key in <home>/.dev_secret_key."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet


def ensure_dev_secret_key(home: str | Path) -> str:
    """Return the dev Fernet master key, creating it if absent.

    The key is persisted to ``<home>/.dev_secret_key`` and reused on subsequent
    calls, making the function idempotent.
    """
    key_file = Path(home) / ".dev_secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = Fernet.generate_key().decode("ascii")
    key_file.write_text(key)
    return key


if __name__ == "__main__":
    import os

    home = os.environ.get("FLEETENT_HOME", os.path.join(os.getcwd(), ".fleetent-dev"))
    print(ensure_dev_secret_key(home))
