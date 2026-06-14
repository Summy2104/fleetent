"""Unified IM module public API surface (identity, connector, config, manager, admin)."""


def test_im_module_exposes_unified_public_api():
    from fleetent.platform import im_gateway_management as im

    identity_fns = (
        "get_or_create",
        "check_allowed_by_user_id",
        "block_im_user",
        "restore_im_user",
        "rebind_im_identity",
        "list_im_identities",
        "list_all",
        "list_pending",
    )
    connector_fns = (
        "upsert_connector",
        "get_connector",
        "list_connectors",
        "report_status",
        "set_enabled",
    )
    config_fns = ("resolve", "resolve_masked", "set_config", "seed_from_env")

    for name in identity_fns + connector_fns + config_fns:
        assert hasattr(im, name), name

    assert hasattr(im, "ConnectorManager")
    assert im.router.prefix == "/admin/im"


def test_im_module_does_not_reexport_identity_db_path():
    from fleetent.platform import im_gateway_management as im

    assert not hasattr(im, "DB_PATH")
