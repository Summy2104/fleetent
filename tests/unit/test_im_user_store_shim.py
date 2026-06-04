"""Legacy fleetent.im_user_store path is a re-export-only shim of identity submodule."""


def test_legacy_path_reexports_same_objects():
    import fleetent.im_user_store as legacy
    from fleetent.platform.im_gateway_management import identity

    assert legacy.get_or_create is identity.get_or_create
    assert legacy.block_im_user is identity.block_im_user
    assert legacy.list_all is identity.list_all
    # internal name still reachable for not-yet-migrated callers (e.g. blocklist)
    assert legacy._init_db is identity._init_db
