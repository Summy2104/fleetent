from pydantic import BaseModel, Field


class OidcSettings(BaseModel):
    """Platform OIDC login settings.

    ``client_secret_env`` is the env var name holding the OIDC client secret.
    """

    enabled: bool = False
    issuer: str = ""
    client_id: str = ""
    client_secret_env: str = ""
    redirect_uri: str = ""
    button_label: str = ""
    allowed_email_domains: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email"])
    tenant: str = "default"
