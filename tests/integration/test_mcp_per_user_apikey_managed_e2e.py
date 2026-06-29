"""Integration: managed per-user MCP api-key happy-path end-to-end (platform chain).

Exercises the managed credential chain through the platform app:

* mode 1 (form): a node registers a pending (reusing the OAuth pending store), the user
  submits the public ``/mcp/credential`` form (state→triple), the key is stored as a static
  credential, and the node later fetches it through the same ``oauth-token`` path that serves
  OAuth tokens (static keys are returned as-is, never refreshed).
* mode 2 (in-DM tool): the agent forwards a key directly via the node ``credential-set`` hop.

Contract guards: the plaintext key is encrypted at rest (never leaves the platform store in
the clear) and never echoed in the form response; the agent-side credential modules MUST NOT
import platform; static ``api_key`` parsing does not regress.
"""

from __future__ import annotations

import sqlite3

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fleetent.platform.node_management import node_store
from fleetent.server import app
from tests.integration._migration_template import apply_migrations


def _client(tmp_path, monkeypatch) -> tuple[TestClient, str]:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    apply_migrations(db_path)
    return TestClient(app, raise_server_exceptions=True), str(db_path)


def test_managed_apikey_form_happy_path(tmp_path, monkeypatch) -> None:
    client, db_path = _client(tmp_path, monkeypatch)
    key, _ = node_store.register_node("node-a", name="Node A")
    bearer = {"Authorization": f"Bearer {key}"}

    # 1) Agent (via node) registers the one-shot state→triple pending (OAuth fields empty for
    #    an api-key submission) — the same hop the managed state store uses.
    pend = client.post(
        "/nodes/node-a/mcp/oauth-pending",
        headers=bearer,
        json={
            "state": "st-cred",
            "code_verifier": "",
            "user_id": "u1",
            "agent_id": "alpha",
            "server_id": "acme",
            "token_url": "",
            "client_id": "",
            "client_secret_env": "",
            "redirect_uri": "https://platform/mcp/credential",
        },
    )
    assert pend.status_code == 200

    # 2) The user opens the DM link and submits the public form -> key stored (static).
    submit = client.post("/mcp/credential", data={"state": "st-cred", "key": "USER-KEY"})
    assert submit.status_code == 200
    assert "USER-KEY" not in submit.text  # key never echoed back

    # 3) Later, the agent (via node) fetches the key through the shared token path (as-is).
    tok = client.post(
        "/nodes/node-a/mcp/oauth-token",
        headers=bearer,
        json={"user_id": "u1", "agent_id": "alpha", "server_id": "acme"},
    )
    assert tok.status_code == 200
    assert tok.json()["access_token"] == "USER-KEY"

    # Plaintext key is encrypted at rest — it never leaves the platform store in the clear.
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT access_token_ciphertext, credential_kind FROM mcp_user_tokens WHERE user_id='u1'"
    ).fetchone()
    conn.close()
    assert "USER-KEY" not in row[0]
    assert row[1] == "static"

    # State is one-time: a replayed submit no longer succeeds.
    replay = client.post("/mcp/credential", data={"state": "st-cred", "key": "EVIL"})
    assert replay.status_code == 400


def test_managed_apikey_tool_credential_set_happy_path(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    key, _ = node_store.register_node("node-b", name="Node B")
    bearer = {"Authorization": f"Bearer {key}"}

    # mode 2: the agent forwards the user's key directly (no state) via the node hop.
    set_resp = client.post(
        "/nodes/node-b/mcp/credential-set",
        headers=bearer,
        json={"user_id": "u2", "agent_id": "beta", "server_id": "acme", "key": "TOOL-KEY"},
    )
    assert set_resp.status_code == 200

    tok = client.post(
        "/nodes/node-b/mcp/oauth-token",
        headers=bearer,
        json={"user_id": "u2", "agent_id": "beta", "server_id": "acme"},
    )
    assert tok.status_code == 200
    assert tok.json()["access_token"] == "TOOL-KEY"


def test_credential_modules_do_not_import_platform() -> None:
    # Contract: agent-side credential modules MUST NOT import platform.* (agent⊥platform).
    import ast
    import pathlib

    for rel in (
        "src/fleetent/integrations/mcp/credential_submission.py",
        "src/fleetent/integrations/mcp/standalone_credential.py",
    ):
        tree = ast.parse(pathlib.Path(rel).read_text())
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        assert not any(m.startswith("fleetent.platform") for m in imported), (rel, imported)


def test_static_api_key_auth_does_not_regress() -> None:
    # The pre-existing static api_key variant (shared machine key via key_env) still parses
    # and is distinct from the new per-user variant.
    from fleetent.mcp_auth_models import (
        ApiKeyMcpAuthConfig,
        ApiKeyPerUserMcpAuthConfig,
        parse_mcp_auth_config,
    )

    static = parse_mcp_auth_config("api_key", {"key_env": "ACME_KEY"})
    assert isinstance(static, ApiKeyMcpAuthConfig)
    assert static.key_env == "ACME_KEY"

    per_user = parse_mcp_auth_config("api_key_per_user", {"header_style": "x_api_key"})
    assert isinstance(per_user, ApiKeyPerUserMcpAuthConfig)
    assert per_user.header_style == "x_api_key"
