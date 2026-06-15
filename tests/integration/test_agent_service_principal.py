"""Integration tests for agent service-principal casting and run_as credential dispatch (P4)."""

from __future__ import annotations

import base64

import pytest

from tests.integration._migration_template import apply_migrations


@pytest.fixture
def principal_db(tmp_path, monkeypatch):
    db_path = tmp_path / "mgmt.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )
    return db_path


@pytest.fixture(autouse=True)
def restore_delete_hook():
    from fleetent import agent_store

    before = agent_store._delete_agent_hook
    yield
    agent_store._delete_agent_hook = before


# ---------------------------------------------------------------------------
# Task 1.1 — service-principal casting: idempotent creation, role, no api_key
# ---------------------------------------------------------------------------


def test_service_principal_idempotent_creation(principal_db):
    """get_or_create_service_principal creates id='agent:42', role='service'."""
    from fleetent import user_store

    uid = user_store.get_or_create_service_principal(42)

    assert uid == "agent:42"
    user = user_store.get_by_id("agent:42")
    assert user is not None
    assert user.role == "service"

    # Idempotent: second call returns same id, no duplicate rows.
    uid2 = user_store.get_or_create_service_principal(42)
    assert uid2 == "agent:42"


def test_service_principal_has_no_api_key(principal_db):
    """Service principals are created without any inbound ma- key."""
    from fleetent import user_store
    from fleetent.config import Settings
    from fleetent.db import create_database

    user_store.get_or_create_service_principal(99)

    db = create_database(Settings().database_url)
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM api_keys WHERE user_id = :uid",
        {"uid": "agent:99"},
    ).fetchone()
    assert row["cnt"] == 0


# ---------------------------------------------------------------------------
# Task 1.2 — set_role guard: service principals cannot be promoted
# ---------------------------------------------------------------------------


def test_service_principal_cannot_be_promoted_to_human_role(principal_db):
    """set_role on a service principal must raise PermissionError."""
    from fleetent import user_store

    user_store.get_or_create_service_principal(7)

    with pytest.raises(PermissionError, match="service principal"):
        user_store.set_role("agent:7", "viewer")


def test_service_principal_cannot_be_promoted_to_admin(principal_db):
    from fleetent import user_store

    user_store.get_or_create_service_principal(8)

    with pytest.raises(PermissionError, match="service principal"):
        user_store.set_role("agent:8", "admin")


# ---------------------------------------------------------------------------
# Task 2.1 — run_as dispatch: user vs agent principal, no cross-contamination
# ---------------------------------------------------------------------------


def test_run_as_user_resolves_caller_credential(principal_db):
    """run_as='user' uses the calling user's stored credential."""
    import importlib

    from fleetent.platform.connector_management import (
        agent_service_grant_store,
        external_credential_store,
        external_service_store,
    )
    from fleetent import agent_store, connectors

    provider = importlib.import_module("fleetent.platform.connector_management.vault_provider")

    external_service_store.add_service("gh", "GitHub", protocol="apikey")
    agent = agent_store.create_agent("runner", "p", [])
    agent_service_grant_store.bind(agent.id, "gh", run_as="user")

    # Store a credential for the caller user, not the agent principal.
    external_credential_store.put_apikey_credential("caller-u1", "gh", "key-for-user")

    result = provider.get_credential("caller-u1", "gh", [], "runner")

    assert isinstance(result, connectors.Credential)
    assert result.client["api_key"] == "key-for-user"


def test_run_as_agent_resolves_service_principal_credential(principal_db):
    """run_as='agent' uses the agent's own service-principal credential, not the caller's."""
    import importlib

    from fleetent.platform.connector_management import (
        agent_service_grant_store,
        external_credential_store,
        external_service_store,
    )
    from fleetent import agent_store, connectors, user_store

    provider = importlib.import_module("fleetent.platform.connector_management.vault_provider")

    external_service_store.add_service("gh", "GitHub", protocol="apikey")
    agent = agent_store.create_agent("runner", "p", [])
    agent_service_grant_store.bind(agent.id, "gh", run_as="agent")

    # Create the service principal and store a credential for it.
    principal_id = user_store.get_or_create_service_principal(agent.id)
    external_credential_store.put_apikey_credential(principal_id, "gh", "key-for-agent")

    # Caller has no credential of their own.
    result = provider.get_credential("caller-u1", "gh", [], "runner")

    assert isinstance(result, connectors.Credential)
    assert result.client["api_key"] == "key-for-agent"


def test_run_as_agent_no_credential_returns_needs_consent(principal_db):
    """run_as='agent' with no stored credential returns NeedsConsent, not the caller's cred."""
    import importlib

    from fleetent.platform.connector_management import (
        agent_service_grant_store,
        external_credential_store,
        external_service_store,
    )
    from fleetent import agent_store, connectors

    provider = importlib.import_module("fleetent.platform.connector_management.vault_provider")

    external_service_store.add_service("gh", "GitHub", protocol="apikey")
    agent = agent_store.create_agent("runner", "p", [])
    agent_service_grant_store.bind(agent.id, "gh", run_as="agent")

    # Store a credential for the caller — must NOT be returned for run_as=agent.
    external_credential_store.put_apikey_credential("caller-u1", "gh", "caller-key")

    result = provider.get_credential("caller-u1", "gh", [], "runner")

    assert isinstance(result, connectors.NeedsConsent)
    assert result.connector == "gh"


def test_run_as_user_does_not_leak_agent_credential(principal_db):
    """run_as='user' must not return the agent's service-principal credential."""
    import importlib

    from fleetent.platform.connector_management import (
        agent_service_grant_store,
        external_credential_store,
        external_service_store,
    )
    from fleetent import agent_store, connectors, user_store

    provider = importlib.import_module("fleetent.platform.connector_management.vault_provider")

    external_service_store.add_service("gh", "GitHub", protocol="apikey")
    agent = agent_store.create_agent("runner", "p", [])
    agent_service_grant_store.bind(agent.id, "gh", run_as="user")

    # Store a credential only for the agent service-principal.
    principal_id = user_store.get_or_create_service_principal(agent.id)
    external_credential_store.put_apikey_credential(principal_id, "gh", "agent-only-key")

    # Caller has no credential; run_as=user so agent principal credential is NOT used.
    result = provider.get_credential("caller-u1", "gh", [], "runner")

    assert isinstance(result, connectors.NeedsConsent)


def test_no_grant_falls_back_to_caller_credential(principal_db):
    """When agent has no grant for a service, caller's credential is used unchanged."""
    import importlib

    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )
    from fleetent import agent_store, connectors

    provider = importlib.import_module("fleetent.platform.connector_management.vault_provider")

    external_service_store.add_service("gh", "GitHub", protocol="apikey")
    agent_store.create_agent("runner", "p", [])
    # No bind() call → no grant.

    external_credential_store.put_apikey_credential("caller-u1", "gh", "caller-key")

    result = provider.get_credential("caller-u1", "gh", [], "runner")

    assert isinstance(result, connectors.Credential)
    assert result.client["api_key"] == "caller-key"


# ---------------------------------------------------------------------------
# Task 3.1 — delete_agent: best-effort cleanup of service-principal credentials
# ---------------------------------------------------------------------------


def test_delete_agent_cleans_up_service_principal_credentials(principal_db):
    """After delete_agent, the service-principal's external_credentials are gone."""
    from fleetent import agent_store, user_store
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
    )

    external_service_store.add_service("gh", "GitHub", protocol="apikey")
    agent = agent_store.create_agent("doomed", "p", [])
    principal_id = user_store.get_or_create_service_principal(agent.id)
    external_credential_store.put_apikey_credential(principal_id, "gh", "secret-key")

    # Register the cleanup hook (mirrors what server.py lifespan does at startup).
    def _cleanup(aid: int) -> None:
        external_credential_store.delete_all_credentials_for_user(f"agent:{aid}")

    agent_store.set_delete_agent_hook(_cleanup)

    assert agent_store.delete_agent("doomed") is True

    # Credential for service principal must be gone.
    assert external_credential_store.get_credential(principal_id, "gh") is None


def test_delete_agent_cleanup_failure_does_not_raise(principal_db):
    """A failing cleanup hook must not propagate; delete_agent still returns True."""
    from fleetent import agent_store

    agent_store.create_agent("doomed2", "p", [])

    def _bad_hook(aid: int) -> None:
        raise RuntimeError("simulated cleanup failure")

    agent_store.set_delete_agent_hook(_bad_hook)

    result = agent_store.delete_agent("doomed2")
    assert result is True


def test_delete_agent_without_hook_succeeds(principal_db):
    """delete_agent works fine when no cleanup hook is registered."""
    from fleetent import agent_store

    agent_store._delete_agent_hook = None
    agent_store.create_agent("plain", "p", [])
    assert agent_store.delete_agent("plain") is True
