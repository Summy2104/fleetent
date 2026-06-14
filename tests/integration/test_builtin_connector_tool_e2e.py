"""End-to-end dispatch tests for the builtin connector tool."""

from __future__ import annotations

import base64
import json

import pytest

from fleetent import connectors
from fleetent import eval_logger
from fleetent.tools import builtin_tools  # noqa: F401  # load-bearing registration
from fleetent.tools import registry as tool_registry
from tests.integration._migration_template import apply_migrations


@pytest.fixture(autouse=True)
def restore_provider():
    before = connectors._provider
    yield
    connectors._provider = before


def test_builtin_connector_tool_uses_per_user_credential_and_hides_secret(tmp_path, monkeypatch):
    from fleetent.platform.connector_management import (
        external_credential_store,
        external_service_store,
        vault_provider,
    )

    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )

    external_service_store.add_service("github", "GitHub")
    external_credential_store.put_oauth_credential(
        "u1",
        "github",
        {"access_token": "token-u1", "refresh_token": "refresh-u1", "scope": "repo"},
        updated_by="u1",
    )
    connectors.set_provider(vault_provider.get_credential)

    result = tool_registry.dispatch("github_connection_status", "{}", user_id="u1")

    assert "github credential ready" in result
    assert "token-u1" not in result
    assert "refresh-u1" not in result

    serialized = json.dumps(eval_logger._serialize({"role": "tool", "content": result}))
    assert "token-u1" not in serialized
    assert "refresh-u1" not in serialized


def test_builtin_connector_tool_returns_consent_prompt_when_unauthorized(
    tmp_path, monkeypatch
):
    from fleetent.platform.connector_management import vault_provider

    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    connectors.set_provider(vault_provider.get_credential)

    result = tool_registry.dispatch("github_connection_status", "{}", user_id="u1")

    assert "requires authorization" in result
    assert "github" in result
