"""Bridge from agent_mcp_server_store global definitions into the live MCP client."""

import pytest

import fleetent.integrations.mcp.client as mcp_client
from fleetent.platform.connector_management import agent_mcp_server_store as store
from fleetent.platform.connector_management import mcp_runtime
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


@pytest.fixture(autouse=True)
def clean_registry():
    import fleetent.tools.registry as tr

    before, srv = dict(tr._registry), dict(mcp_client._server_registry)
    yield
    tr._registry.clear()
    tr._registry.update(before)
    mcp_client._server_registry.clear()
    mcp_client._server_registry.update(srv)


def test_row_to_config_maps_fields(db):
    store.add_mcp_server(None, "s1", transport="http", url="https://x/mcp", api_key_env="K")
    cfg = mcp_runtime._row_to_config(store.get_mcp_server(None, "s1"))
    assert cfg.id == "s1"
    assert cfg.transport == "http"
    assert cfg.url == "https://x/mcp"
    assert cfg.api_key_env == "K"


def test_enabled_global_configs_skips_disabled(db):
    store.add_mcp_server(None, "on", url="https://a")
    store.add_mcp_server(None, "off", url="https://b", enabled=False)
    ids = {c.id for c in mcp_runtime.enabled_global_configs()}
    assert ids == {"on"}


async def test_sync_server_registers_then_unregisters(db, monkeypatch):
    registered = []

    async def fake_register_all(configs, scope=None):
        for c in configs:
            mcp_client._server_registry[(scope, c.id)] = c
            registered.append(c.id)

    monkeypatch.setattr(mcp_runtime, "register_all", fake_register_all)

    store.add_mcp_server(None, "live", url="https://a")
    await mcp_runtime.sync_server("live")
    assert (None, "live") in mcp_client._server_registry

    # disable -> sync should unregister
    store.edit_mcp_server(None, "live", enabled=False)
    await mcp_runtime.sync_server("live")
    assert (None, "live") not in mcp_client._server_registry


def test_row_to_config_maps_headers(db):
    store.add_mcp_server(None, "hx", transport="http", url="https://a", headers={"X-API-Key": "k"})
    cfg = mcp_runtime._row_to_config(store.get_mcp_server(None, "hx"))
    assert cfg.headers == {"X-API-Key": "k"}
