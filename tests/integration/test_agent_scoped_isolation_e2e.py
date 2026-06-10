"""End-to-end agent-scoped isolation (Task 8.1).

Two agents (A, B) share the same ``github`` connector id and the same ``github``
MCP server id but carry distinct credentials. The full stack — Alembic schema,
scoped connector store, scoped MCP server store, scope-keyed MCP client — must
route each agent to its own session/credential. Crucially, agent B's call must
never be satisfied by agent A's authorization.
"""

import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

import fleetent.integrations.mcp.client as mcp_client
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.platform.connector_management import (
    agent_mcp_server_store,
    connector_config_store,
)
from tests.integration._migration_template import apply_migrations as _apply_migrations

AGENT_A = 1
AGENT_B = 2


@pytest.fixture
def scoped_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    _apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # isolate MCP client maps
    srv_before = dict(mcp_client._server_registry)
    sess_before = dict(mcp_client._active_sessions)
    yield db_path
    mcp_client._server_registry.clear()
    mcp_client._server_registry.update(srv_before)
    mcp_client._active_sessions.clear()
    mcp_client._active_sessions.update(sess_before)


async def test_two_agents_same_github_route_to_separate_credentials(scoped_db, monkeypatch):
    # Connector config catalog: same id, per-agent client_id, no shared row.
    connector_config_store.add_connector(
        "github", "GitHub (A)", oauth_config={"client_id": "cid-A"}, agent_id=AGENT_A
    )
    connector_config_store.add_connector(
        "github", "GitHub (B)", oauth_config={"client_id": "cid-B"}, agent_id=AGENT_B
    )
    a_cfg = connector_config_store.get_connector("github", agent_id=AGENT_A)
    b_cfg = connector_config_store.get_connector("github", agent_id=AGENT_B)
    assert a_cfg["oauth_config"]["client_id"] == "cid-A"
    assert b_cfg["oauth_config"]["client_id"] == "cid-B"

    # MCP server catalog: same server_id, per-agent endpoint + credential env var.
    agent_mcp_server_store.add_mcp_server(
        AGENT_A,
        "github",
        transport="http",
        url="http://gh-a.test",
        auth_type="api_key",
        api_key_env="GH_TOKEN_A",
    )
    agent_mcp_server_store.add_mcp_server(
        AGENT_B,
        "github",
        transport="http",
        url="http://gh-b.test",
        auth_type="api_key",
        api_key_env="GH_TOKEN_B",
    )
    monkeypatch.setenv("GH_TOKEN_A", "tok-A")
    monkeypatch.setenv("GH_TOKEN_B", "tok-B")

    def _server_for(agent_id: int) -> McpServerConfig:
        row = agent_mcp_server_store.get_mcp_server(agent_id, "github")
        return McpServerConfig(
            id=row["server_id"],
            transport=row["transport"],
            url=row["url"],
            auth_type=row["auth_type"],
            api_key_env=row["api_key_env"],
        )

    # Mock at the SDK seam (the client now runs on the official mcp SDK; a raw
    # respx JSON-RPC echo no longer satisfies the streamable-HTTP handshake and
    # the transport's retry loop hangs the test). Each fake connection captures
    # the Authorization header it was opened with; its session echoes that
    # credential back as the whoami result.
    class _EchoSession:
        def __init__(self, auth: str) -> None:
            self._auth = auth

        async def initialize(self) -> Any:
            return SimpleNamespace(protocolVersion="2025-11-25", capabilities={})

        async def list_tools(self, cursor: str | None = None) -> Any:
            tool = SimpleNamespace(
                name="whoami",
                description="echo credential",
                inputSchema={"type": "object", "properties": {}},
            )
            return SimpleNamespace(tools=[tool], nextCursor=None)

        async def call_tool(self, name: str, args: dict, **kw: Any) -> Any:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=self._auth)],
                structuredContent=None,
                isError=False,
            )

    pending_auth: list[str] = []

    def fake_streamable(*args: Any, **kwargs: Any) -> Any:
        headers = kwargs.get("headers") or {}
        pending_auth.append(headers.get("Authorization", ""))

        @contextlib.asynccontextmanager
        async def _cm():
            yield ("read", "write", None)

        return _cm()

    def fake_client_session(*args: Any, **kwargs: Any) -> Any:
        auth = pending_auth[-1]

        @contextlib.asynccontextmanager
        async def _cm():
            yield _EchoSession(auth)

        return _cm()

    monkeypatch.setattr(mcp_client, "streamablehttp_client", fake_streamable)
    monkeypatch.setattr(mcp_client, "ClientSession", fake_client_session)

    # Only agent A is registered so far.
    await mcp_client.register_all([_server_for(AGENT_A)], scope=AGENT_A)

    # Agent B has no registration yet — its call must NOT fall through to A.
    with pytest.raises(KeyError):
        await mcp_client.call_tool("github", "whoami", {}, scope=AGENT_B)

    await mcp_client.register_all([_server_for(AGENT_B)], scope=AGENT_B)

    a_result = await mcp_client.call_tool("github", "whoami", {}, scope=AGENT_A)
    b_result = await mcp_client.call_tool("github", "whoami", {}, scope=AGENT_B)

    assert a_result == "Bearer tok-A"
    assert b_result == "Bearer tok-B"
    assert a_result != b_result


async def test_dispatch_guard_blocks_out_of_scope_mcp_server(scoped_db, monkeypatch):
    import fleetent.tools.registry as tr

    # Agent A's resolved scope only includes "github"; "internal" is out of scope.
    with pytest.raises(PermissionError):
        await _maybe_await(
            tr.dispatch(
                "internal__read",
                "{}",
                mcp_server_ids=["github"],
                mcp_scope=AGENT_A,
            )
        )


async def _maybe_await(value):  # type: ignore[no-untyped-def]
    if hasattr(value, "__await__"):
        return await value
    return value
