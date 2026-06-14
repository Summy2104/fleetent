"""connector_store submodule of the unified IM module (ex im_connector_store)."""


def test_connector_store_submodule_exposes_public_fns():
    from fleetent.platform.im_gateway_management import connector_store

    for name in (
        "upsert_connector",
        "report_status",
        "heartbeat",
        "set_enabled",
        "get_connector",
        "list_connectors",
        "STATUSES",
    ):
        assert hasattr(connector_store, name), name


def test_connector_store_db_path_monkeypatchable(tmp_path, monkeypatch):
    from fleetent.platform.im_gateway_management import connector_store

    monkeypatch.setattr(connector_store, "DB_PATH", tmp_path / "users.db")
    assert tmp_path / "users.db" == connector_store.DB_PATH


def test_legacy_connector_store_path_reexports_same_objects():
    from fleetent.platform.im_gateway_management import connector_store, im_connector_store

    assert im_connector_store.upsert_connector is connector_store.upsert_connector
    assert im_connector_store.get_connector is connector_store.get_connector
