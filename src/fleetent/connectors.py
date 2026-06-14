"""Tool OAuth credential contract and a swappable provider seam.

This module is about *tool* connector credentials (e.g. google-drive, github):
the OAuth client a tool needs at execution time. It is unrelated to platform IM
identity mapping and IM-user administration.

`get_credential` delegates to a module-level, monkeypatch-able `_provider`. The
default provider always returns `NeedsConsent` because real OAuth token storage
and refresh are out of scope here (a later connector-oauth-store change supplies
a real provider through this same seam).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

CredentialProvider = Callable[[str, str, "list[str]"], "Credential | NeedsConsent"]


@dataclass
class Credential:
    """An authorized credential carrying a ready-to-use client for a tool.

    `client` is whatever object the tool expects (connector-specific). `secret`,
    if present, is masked from `repr`/`str` so it can never leak into logs,
    traces, or exception text.
    """

    connector: str
    client: Any
    secret: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return f"Credential(connector={self.connector!r}, client=<redacted>)"

    __str__ = __repr__


@dataclass
class NeedsConsent:
    """Signals the user has not yet authorized this connector.

    `dispatch` returns the `consent_url` to the LLM and skips tool execution.
    """

    connector: str
    consent_url: str


def _default_provider(user_id: str, connector: str, scopes: list[str]) -> Credential | NeedsConsent:
    """Default seam: no OAuth store yet, so always require consent."""
    return NeedsConsent(
        connector=connector,
        consent_url=f"https://consent.invalid/{connector}",
    )


_provider: CredentialProvider = _default_provider


def set_provider(provider: CredentialProvider) -> None:
    """Replace the credential provider seam (used by the OAuth store change/tests)."""
    global _provider
    _provider = provider


def get_credential(
    user_id: str | None, connector: str, scopes: list[str]
) -> Credential | NeedsConsent:
    """Resolve a connector credential for a user.

    Without a `user_id` credentials cannot be isolated per user, so we degrade
    safely to `NeedsConsent` without consulting the provider.
    """
    if user_id is None:
        return NeedsConsent(
            connector=connector,
            consent_url=f"https://consent.invalid/{connector}",
        )
    return _provider(user_id, connector, scopes)
