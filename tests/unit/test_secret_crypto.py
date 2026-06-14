from __future__ import annotations

import base64
import importlib
import importlib.util

import pytest


def _secret_crypto_module():
    spec = importlib.util.find_spec("fleetent.secret_crypto")
    assert spec is not None, "fleetent.secret_crypto module is missing"
    return importlib.import_module("fleetent.secret_crypto")


def test_encrypt_decrypt_round_trip_uses_fleetent_secret_key(monkeypatch):
    secret_crypto = _secret_crypto_module()
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )

    ciphertext = secret_crypto.encrypt_text("sk-live-secret")

    assert ciphertext != "sk-live-secret"
    assert "sk-live-secret" not in ciphertext
    assert secret_crypto.decrypt_text(ciphertext) == "sk-live-secret"


def test_missing_secret_key_raises_clear_error(monkeypatch):
    secret_crypto = _secret_crypto_module()
    monkeypatch.delenv("FLEETENT_SECRET_KEY", raising=False)

    with pytest.raises(secret_crypto.SecretKeyError, match="FLEETENT_SECRET_KEY"):
        secret_crypto.encrypt_text("sk-live-secret")


def test_invalid_secret_key_raises_clear_error(monkeypatch):
    secret_crypto = _secret_crypto_module()
    monkeypatch.setenv("FLEETENT_SECRET_KEY", "not-a-fernet-key")

    with pytest.raises(secret_crypto.SecretKeyError, match="FLEETENT_SECRET_KEY"):
        secret_crypto.decrypt_text("gAAAAABpFakeCiphertext")
