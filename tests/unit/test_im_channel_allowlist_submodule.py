"""channel_allowlist submodule of the unified IM module (ex im_channel_allowlist)."""


def test_channel_allowlist_submodule_exposes_public_fns():
    from fleetent.platform.im_gateway_management import channel_allowlist

    for name in ("add_entry", "remove_entry", "list_entries", "is_allowed"):
        assert hasattr(channel_allowlist, name), name


def test_legacy_channel_allowlist_path_reexports_same_objects():
    from fleetent.platform.im_gateway_management import channel_allowlist, im_channel_allowlist

    assert im_channel_allowlist.add_entry is channel_allowlist.add_entry
    assert im_channel_allowlist.is_allowed is channel_allowlist.is_allowed
