"""Unit tests for scripts/dev_secret_key.py::ensure_dev_secret_key."""

from __future__ import annotations

import sys
from pathlib import Path

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_ensure_dev_secret_key_creates_valid_fernet_key(tmp_path) -> None:
    from dev_secret_key import ensure_dev_secret_key

    key = ensure_dev_secret_key(tmp_path)

    assert (tmp_path / ".dev_secret_key").exists()
    Fernet(key.encode("ascii"))  # raises if invalid


def test_ensure_dev_secret_key_is_idempotent(tmp_path) -> None:
    from dev_secret_key import ensure_dev_secret_key

    first = ensure_dev_secret_key(tmp_path)
    second = ensure_dev_secret_key(tmp_path)

    assert first == second
    assert (tmp_path / ".dev_secret_key").read_text().strip() == first
