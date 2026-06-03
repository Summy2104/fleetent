import pytest

import fleetent.platform.im_gateway_management.channel_allowlist as acl
import fleetent.platform.im_gateway_management.connector_store as ics
import fleetent.user_store as user_store
from fleetent.im_gateway import normalizer
from fleetent.platform.im_gateway_management import identity as im_user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    for mod in (user_store, ics, acl):
        monkeypatch.setattr(mod, "DB_PATH", tmp_path / "users.db")
    ics._init_db()
    acl._init_db()
    return tmp_path / "users.db"


_OWNER = "owner1"


def _msg(replies, *, channel_id="C_ops", workspace_id=""):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        owner_id=_OWNER,
        session_id="thread:1",
        user_id="u1",
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id=channel_id,
        workspace_id=workspace_id,
    )


async def test_disallowed_channel_rejected_before_user_check(db, monkeypatch):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=True)  # no allowlist entries
    called = {"user_check": False}

    def spy(_uid):
        called["user_check"] = True
        return True

    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", spy)
    replies = []
    await normalizer.route(_msg(replies))
    assert called["user_check"] is False  # returned before user-level check
    assert replies and replies[0] == normalizer._REJECTION_MSG


async def test_allowed_channel_proceeds_to_user_check(db, monkeypatch):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=True)
    acl.add_entry(_OWNER, "slack", "channel", "C_ops")
    called = {"user_check": False}

    def spy(_uid):
        called["user_check"] = True
        return False  # stop here so we don't enter the agent loop

    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", spy)
    replies = []
    await normalizer.route(_msg(replies))
    assert called["user_check"] is True  # passed the channel gate


async def test_not_enforced_passes_channel_gate(db, monkeypatch):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=False)
    called = {"user_check": False}

    def spy(_uid):
        called["user_check"] = True
        return False

    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", spy)
    replies = []
    await normalizer.route(_msg(replies, channel_id="C_whatever"))
    assert called["user_check"] is True


async def test_workspace_allow_covers_channel(db, monkeypatch):
    ics.upsert_connector(_OWNER, "slack", allowlist_enforced=True)
    acl.add_entry(_OWNER, "slack", "workspace", "T_team")
    called = {"user_check": False}

    def spy(_uid):
        called["user_check"] = True
        return False

    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", spy)
    replies = []
    await normalizer.route(_msg(replies, channel_id="C_any", workspace_id="T_team"))
    assert called["user_check"] is True
