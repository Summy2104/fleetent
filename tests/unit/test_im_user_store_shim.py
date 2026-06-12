"""Legacy fleetent.im_user_store path is a re-export-only shim of identity submodule."""

from pathlib import Path


def test_legacy_path_reexports_same_objects():
    import fleetent.im_user_store as legacy
    from fleetent.platform.im_gateway_management import identity

    assert legacy.get_or_create is identity.get_or_create
    assert legacy.block_im_user is identity.block_im_user
    assert legacy.list_all is identity.list_all
    assert not hasattr(legacy, "_init_db")


def test_identity_store_is_crud_only_and_shim_drops_schema_helpers():
    source = Path("src/fleetent/platform/im_gateway_management/identity.py").read_text()

    assert "CREATE TABLE" not in source
    assert "def _init_db" not in source
    assert "DB_PATH as DB_PATH" not in source
    assert "?" not in source
    assert ":owner_id" in source
