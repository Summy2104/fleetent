"""Per-agent IM wiring remains intact after owner-level connector removal."""

import fleetent.server as srv

_OWNER_ROUTE = "/admin/im/" + "connectors"
_OWNER_MANAGER_ATTR = "_connector" + "_manager"


def test_per_agent_platforms_removed_from_owner_manager():
    assert hasattr(srv, "_slack_supervisor")
    assert not hasattr(srv, _OWNER_MANAGER_ATTR)


def test_owner_level_im_routes_removed():
    paths = {getattr(route, "path", None) for route in srv.app.routes}
    assert _OWNER_ROUTE not in paths
