"""Integration: managed OAuth client_secret resolves by agent *name* scope.

Exercises the composition-root resolver `server._resolve_agent_client_secret` against a
real management DB (`agent_store` + `agent_secrets`). The runtime OAuth triple carries the
agent identity as a name, so the resolver must map name→registry id before the per-agent
secret lookup, with a global-scope fallback. This is the managed-oauth-agent-identity fix
for the pre-fix behavior that dropped name identities straight to the global scope.
"""

import base64

import pytest

import fleetent.agent_store as agent_store
import fleetent.server as server
from fleetent.platform.agent_lifecycle import secret_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )
    return db_path


def test_resolves_per_agent_secret_by_name(db):
    agent = agent_store.create_agent("bi-intern", "p", [])
    secret_store.set(agent.id, "GDRIVE_CLIENT_SECRET", "per-agent-secret")

    # The triple carries the *name*, not the numeric id.
    out = server._resolve_agent_client_secret("bi-intern", "GDRIVE_CLIENT_SECRET")
    assert out == "per-agent-secret"


def test_resolves_by_numeric_identity(db):
    agent = agent_store.create_agent("bi-intern", "p", [])
    secret_store.set(agent.id, "GDRIVE_CLIENT_SECRET", "per-agent-secret")

    out = server._resolve_agent_client_secret(str(agent.id), "GDRIVE_CLIENT_SECRET")
    assert out == "per-agent-secret"


def test_falls_back_to_global_when_per_agent_missing(db):
    agent_store.create_agent("bi-intern", "p", [])
    # No per-agent value; only a global (agent_id NULL) one exists.
    secret_store.set(None, "GDRIVE_CLIENT_SECRET", "global-secret")

    out = server._resolve_agent_client_secret("bi-intern", "GDRIVE_CLIENT_SECRET")
    assert out == "global-secret"


def test_unknown_agent_name_with_no_global_resolves_none(db):
    out = server._resolve_agent_client_secret("no-such-agent", "GDRIVE_CLIENT_SECRET")
    assert out is None


def test_none_identity_resolves_global(db):
    secret_store.set(None, "GDRIVE_CLIENT_SECRET", "global-secret")
    out = server._resolve_agent_client_secret(None, "GDRIVE_CLIENT_SECRET")
    assert out == "global-secret"
