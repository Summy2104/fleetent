from tests.integration._migration_template import apply_migrations

"""DB-backed channel allowlist submodule behavior."""


def test_enforcement_opt_in_per_owner(tmp_path, monkeypatch):
    from fleetent import user_store
    from fleetent.platform.im_gateway_management import channel_allowlist as al
    from fleetent.platform.im_gateway_management import connector_store as store

    p = tmp_path / "users.db"
    for mod in (user_store, store, al):
        monkeypatch.setattr(mod, "DB_PATH", p)
        apply_migrations(p)
    # No connector row -> not enforced -> everything allowed.
    assert al.is_allowed("ownerA", "slack", "C1") is True
    # Enforce, with one allowed channel.
    store.upsert_connector("ownerA", "slack")
    store.set_allowlist_enforced("ownerA", "slack", True)
    al.add_entry("ownerA", "slack", "channel", "C1")
    assert al.is_allowed("ownerA", "slack", "C1") is True
    assert al.is_allowed("ownerA", "slack", "C2") is False
