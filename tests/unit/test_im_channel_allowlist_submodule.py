"""channel_allowlist submodule of the unified IM module (ex im_channel_allowlist)."""


def test_channel_allowlist_submodule_exposes_public_fns():
    from fleetent.platform.im_gateway_management import channel_allowlist

    for name in ("add_entry", "remove_entry", "list_entries", "is_allowed"):
        assert hasattr(channel_allowlist, name), name


def test_enforcement_opt_in_per_owner(tmp_path, monkeypatch):
    from fleetent import user_store
    from fleetent.platform.im_gateway_management import channel_allowlist as al
    from fleetent.platform.im_gateway_management import connector_store as store

    p = tmp_path / "users.db"
    for mod in (user_store, store, al):
        monkeypatch.setattr(mod, "DB_PATH", p)
    # No connector row -> not enforced -> everything allowed.
    assert al.is_allowed("ownerA", "slack", "C1") is True
    # Enforce, with one allowed channel.
    store.upsert_connector("ownerA", "slack")
    store.set_allowlist_enforced("ownerA", "slack", True)
    al.add_entry("ownerA", "slack", "channel", "C1")
    assert al.is_allowed("ownerA", "slack", "C1") is True
    assert al.is_allowed("ownerA", "slack", "C2") is False


def test_legacy_channel_allowlist_path_reexports_same_objects():
    from fleetent.platform.im_gateway_management import channel_allowlist, im_channel_allowlist

    assert im_channel_allowlist.add_entry is channel_allowlist.add_entry
    assert im_channel_allowlist.is_allowed is channel_allowlist.is_allowed
