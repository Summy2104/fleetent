"""Unit: managed OAuth client_secret resolution delegates the raw agent identity.

The platform service MUST pass the runtime triple's agent identity (a *name* in the
managed path, e.g. ``"bi-intern"``) through to the injected resolver verbatim — the
name→numeric-id scope mapping and global fallback live in the composition-root resolver
(server.py), not here. This guards against the pre-fix ``int(agent_id) if isdigit``
gate that silently dropped name identities to the global scope.
"""

from __future__ import annotations

import pytest

from fleetent.platform.connector_management import mcp_oauth_service as svc


@pytest.fixture(autouse=True)
def _reset_resolver():
    svc.set_client_secret_resolver(None)
    yield
    svc.set_client_secret_resolver(None)


def test_passes_agent_name_verbatim_to_resolver() -> None:
    seen: list[tuple[object, str]] = []

    def resolver(agent_ref, env_name):
        seen.append((agent_ref, env_name))
        return "the-secret"

    svc.set_client_secret_resolver(resolver)
    out = svc._resolve_client_secret("bi-intern", "GDRIVE_CLIENT_SECRET")

    assert out == "the-secret"
    # Raw name reaches the resolver — NOT mapped to None by an isdigit() gate.
    assert seen == [("bi-intern", "GDRIVE_CLIENT_SECRET")]


def test_passes_numeric_identity_verbatim() -> None:
    seen: list[tuple[object, str]] = []
    svc.set_client_secret_resolver(lambda a, e: seen.append((a, e)) or "s")

    svc._resolve_client_secret("6", "ENV")

    assert seen == [("6", "ENV")]


def test_empty_env_ref_returns_empty_without_calling_resolver() -> None:
    called = False

    def resolver(agent_ref, env_name):
        nonlocal called
        called = True
        return "x"

    svc.set_client_secret_resolver(resolver)
    assert svc._resolve_client_secret("bi-intern", "") == ""
    assert called is False


def test_no_resolver_returns_empty() -> None:
    svc.set_client_secret_resolver(None)
    assert svc._resolve_client_secret("bi-intern", "ENV") == ""


def test_resolver_none_result_becomes_empty_string() -> None:
    svc.set_client_secret_resolver(lambda a, e: None)
    assert svc._resolve_client_secret("bi-intern", "ENV") == ""
