import pytest

from fleetent.config import Settings
from fleetent.platform.config_validation import validate_config
from fleetent.platform.user_management.oidc import OidcSettings, _oidc_tenant_for


@pytest.fixture(autouse=True)
def isolate_settings_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))


def test_settings_loads_oidc_defaults_and_platform_yaml(tmp_path, monkeypatch):
    import fleetent.config as cfg

    platform_yaml = tmp_path / "platform.yaml"
    platform_yaml.write_text(
        "\n".join(
            [
                "oidc:",
                "  issuer: https://idp.example.com/realms/acme",
                "  client_id: fleetent-web",
                "  client_secret_env: FLEETENT_OIDC_CLIENT_SECRET",
                "  redirect_uri: https://fleetent.example.com/admin/oidc/callback",
                "  button_label: Sign in with Google",
                "  allowed_email_domains:",
                "    - acme.com",
                "    - eu.acme.com",
                "  tenant: acme",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "PLATFORM_YAML_PATH", platform_yaml)

    settings = Settings()

    assert isinstance(settings.oidc, OidcSettings)
    assert settings.oidc.enabled is False
    assert settings.oidc.issuer == "https://idp.example.com/realms/acme"
    assert settings.oidc.client_id == "fleetent-web"
    assert settings.oidc.client_secret_env == "FLEETENT_OIDC_CLIENT_SECRET"
    assert settings.oidc.redirect_uri == "https://fleetent.example.com/admin/oidc/callback"
    assert settings.oidc.button_label == "Sign in with Google"
    assert settings.oidc.allowed_email_domains == ["acme.com", "eu.acme.com"]
    assert settings.oidc.scopes == ["openid", "email"]
    assert settings.oidc.tenant == "acme"


def test_settings_loads_oidc_allowed_email_domains_from_env(monkeypatch):
    monkeypatch.setenv("OIDC__ALLOWED_EMAIL_DOMAINS", '["acme.com","example.org"]')

    settings = Settings()

    assert settings.oidc.allowed_email_domains == ["acme.com", "example.org"]


def test_validate_config_rejects_inline_oidc_secret_like_value(tmp_path):
    platform_yaml = tmp_path / "platform.yaml"
    platform_yaml.write_text(
        "\n".join(
            [
                "oidc:",
                "  issuer: https://idp.example.com/realms/acme",
                "  client_id: fleetent-web",
                "  client_secret_env: sk-live-0123456789abcdefghijABCDEF",
                "  redirect_uri: https://fleetent.example.com/admin/oidc/callback",
                "  tenant: acme",
            ]
        ),
        encoding="utf-8",
    )

    report = validate_config(profile="pilot", config_paths=[platform_yaml])

    item = next(
        entry
        for entry in report.items
        if entry.key == f"config.{platform_yaml}.oidc.client_secret_env"
    )
    assert item.status == "error"
    assert "inline secret-like value" in item.reason


def test_oidc_tenant_for_returns_single_configured_tenant():
    settings = OidcSettings(tenant="acme")

    assert _oidc_tenant_for("person@example.com", {"sub": "oidc-user"}, settings) == "acme"
