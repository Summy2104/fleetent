import pytest

from fleetent import connectors


@pytest.fixture(autouse=True)
def restore_provider():
    """Isolate provider-seam monkeypatching between tests."""
    before = connectors._provider
    yield
    connectors._provider = before


def test_credential_holds_client():
    cred = connectors.Credential(connector="google-drive", client=object())
    assert cred.connector == "google-drive"
    assert cred.client is not None


def test_credential_repr_masks_secret():
    secret = "ya29.super-secret-token"
    cred = connectors.Credential(connector="google-drive", client=object(), secret=secret)
    assert secret not in repr(cred)
    assert secret not in str(cred)
    assert "<redacted>" in repr(cred)


def test_needs_consent_holds_connector_and_url():
    nc = connectors.NeedsConsent(connector="github", consent_url="https://auth/x")
    assert nc.connector == "github"
    assert nc.consent_url == "https://auth/x"


def test_credential_error_repr_masks_details():
    err = connectors.CredentialError(
        connector="github",
        message="refresh request failed",
        retryable=True,
        detail="refresh-u1 secret token",
    )
    assert "refresh-u1" not in repr(err)
    assert "refresh-u1" not in str(err)
    assert "refresh request failed" in repr(err)


def test_default_provider_returns_needs_consent():
    result = connectors.get_credential("user-1", "google-drive", ["drive.readonly"])
    assert isinstance(result, connectors.NeedsConsent)
    assert result.connector == "google-drive"


def test_provider_seam_passthrough(monkeypatch):
    fake = connectors.Credential(connector="github", client=object())

    def _fake_provider(user_id, connector, scopes):
        return fake

    monkeypatch.setattr(connectors, "_provider", _fake_provider)
    result = connectors.get_credential("user-1", "github", [])
    assert result is fake


def test_missing_user_id_returns_needs_consent(monkeypatch):
    def _fake_provider(user_id, connector, scopes):  # pragma: no cover - must not run
        raise AssertionError("provider should not be consulted without user_id")

    monkeypatch.setattr(connectors, "_provider", _fake_provider)
    result = connectors.get_credential(None, "github", [])
    assert isinstance(result, connectors.NeedsConsent)
    assert result.connector == "github"


def test_set_provider_replaces_seam(monkeypatch):
    monkeypatch.setattr(connectors, "_provider", connectors._default_provider)
    fake = connectors.Credential(connector="slack", client=object())
    connectors.set_provider(lambda user_id, connector, scopes: fake)
    assert connectors.get_credential("u", "slack", []) is fake
