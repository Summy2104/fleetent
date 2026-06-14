"""Unified IM module public API surface (identity only)."""


def test_im_module_exposes_unified_public_api():
    from fleetent.platform import im_gateway_management as im

    for name in (
        "get_or_create",
        "check_allowed_by_user_id",
        "block_im_user",
        "restore_im_user",
        "rebind_im_identity",
        "list_im_identities",
        "list_all",
        "list_pending",
    ):
        assert hasattr(im, name), name
    assert not hasattr(im, "router")


def test_im_module_does_not_reexport_identity_db_path():
    from fleetent.platform import im_gateway_management as im

    assert not hasattr(im, "DB_PATH")
