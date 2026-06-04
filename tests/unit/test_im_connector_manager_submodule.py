"""connector_manager submodule of the unified IM module (ex im_connector_manager)."""

import asyncio


def test_connector_manager_submodule_exposes_class():
    from fleetent.platform.im_gateway_management import connector_manager

    assert hasattr(connector_manager, "ConnectorManager")


def test_manager_start_marks_unconfigured_without_factory(monkeypatch):
    from fleetent.platform.im_gateway_management import connector_manager, connector_store

    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        connector_store,
        "report_status",
        lambda owner, platform, status, **kw: calls.append((owner, platform, status)),
    )
    monkeypatch.setattr(connector_manager.connector_config, "resolve", lambda o, p: {})

    m = connector_manager.ConnectorManager()
    asyncio.run(m.start("ownerX", "slack"))
    assert ("ownerX", "slack", "unconfigured") in calls


def test_legacy_connector_manager_path_reexports_same_objects():
    from fleetent.platform.im_gateway_management import connector_manager, im_connector_manager

    assert im_connector_manager.ConnectorManager is connector_manager.ConnectorManager
