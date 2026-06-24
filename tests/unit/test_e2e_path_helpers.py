from pathlib import Path

from tests.e2e import _path_helpers


def test_agent_state_db_path_uses_tenant_first_flat_agent_data() -> None:
    home = Path("/fleetent-home")

    assert _path_helpers.agent_state_db_path(home, "support") == (
        home / "tenants" / "default" / "agents" / "support" / "data" / "agent_state.db"
    )
    assert _path_helpers.agent_state_db_path(home, "support", tenant_id="acme") == (
        home / "tenants" / "acme" / "agents" / "support" / "data" / "agent_state.db"
    )
