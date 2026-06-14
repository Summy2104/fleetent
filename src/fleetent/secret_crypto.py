"""Shared Fernet helpers for encrypted secret persistence."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class SecretKeyError(RuntimeError):
    """Raised when the Fleetent master key is missing, invalid, or cannot decrypt data."""


def _fernet() -> Fernet:
    key = os.environ.get("FLEETENT_SECRET_KEY", "")
    if not key:
        raise SecretKeyError("FLEETENT_SECRET_KEY is required for inject secret operations")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise SecretKeyError("FLEETENT_SECRET_KEY must be a valid Fernet key") from exc


def encrypt_text(plaintext: str) -> str:
    """Encrypt a plaintext string with the shared Fleetent master key."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(ciphertext: str) -> str:
    """Decrypt a ciphertext string with the shared Fleetent master key."""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretKeyError("FLEETENT_SECRET_KEY cannot decrypt the stored secret") from exc
