"""Identity submodule of the unified IM module (ex im_user_store). Behavior-preserving."""


def test_identity_submodule_exposes_public_fns():
    from fleetent.platform.im_gateway_management import identity

    for name in (
        "get_or_create",
        "check_allowed_by_user_id",
        "approve_user",
        "block_user",
        "block_im_user",
        "restore_im_user",
        "batch_block_im",
        "rebind_im_identity",
        "list_im_identities",
        "list_all",
        "list_pending",
    ):
        assert callable(getattr(identity, name)), name


def test_identity_db_path_monkeypatchable(tmp_path, monkeypatch):
    from fleetent.platform.im_gateway_management import identity

    monkeypatch.setattr(identity, "DB_PATH", tmp_path / "users.db")
    assert tmp_path / "users.db" == identity.DB_PATH
