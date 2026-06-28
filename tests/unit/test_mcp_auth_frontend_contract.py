from __future__ import annotations

from pathlib import Path


def test_frontend_mcp_auth_field_sets_match_backend_contract() -> None:
    source = Path("frontend/src/features/connectors/api.ts").read_text()

    assert "api_key: ['key_env']" in source
    assert "oauth_client_credentials: ['token_url', 'client_id', 'client_secret_env', 'scope']" in source
