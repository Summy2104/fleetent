"""admin_api submodule of the unified IM module (ex im_admin_api)."""


def test_admin_api_submodule_exposes_router_and_seams():
    from fleetent.platform.im_gateway_management import admin_api

    assert admin_api.router.prefix == "/admin/im"
    assert hasattr(admin_api, "start_connector")
    assert hasattr(admin_api, "stop_connector")


def test_legacy_admin_api_path_reexports_same_router():
    from fleetent.platform.im_gateway_management import admin_api, im_admin_api

    assert im_admin_api.router is admin_api.router
