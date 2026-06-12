from __future__ import annotations


def test_im_identity_resolver_can_be_left_dirty() -> None:
    from fleetent.im_gateway import access

    access.set_im_identity_resolver(
        lambda owner_id, platform, platform_user_id: f"dirty:{owner_id}:{platform_user_id}"
    )
    assert access.resolve_identity("slack", "U1") == "dirty:default:U1"


def test_im_identity_resolver_starts_each_test_reset_to_passthrough() -> None:
    from fleetent.im_gateway import access

    assert access.resolve_identity("slack", "U1") == "U1"
