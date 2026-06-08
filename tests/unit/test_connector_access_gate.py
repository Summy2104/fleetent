"""Tests for channel_allowed/user_allowed accepting ConnectorAccess (restructure-agent-access)."""

import pytest

from fleetent.agent_config import ConnectorAccess
from fleetent.im_gateway.access import LocalApprovalStore, channel_allowed, user_allowed


# ── Task 2.1: channel_allowed(ConnectorAccess, channel_id) ──────────────────


def test_channel_allowed_empty_allows_all():
    access = ConnectorAccess()
    assert channel_allowed(access, "C_any") is True


def test_channel_allowed_listed_channel():
    access = ConnectorAccess(allow_channels=["C1", "C2"])
    assert channel_allowed(access, "C1") is True


def test_channel_allowed_unlisted_channel_rejected():
    access = ConnectorAccess(allow_channels=["C1"])
    assert channel_allowed(access, "C2") is False


# ── Task 2.2: user_allowed(ConnectorAccess, store, identity) ─────────────────


def test_user_allowed_static_list(tmp_path):
    store = LocalApprovalStore(tmp_path / "approvals.json")
    access = ConnectorAccess(allow_users=["U_alice"])
    assert user_allowed(access, store, "U_alice") is True
    assert user_allowed(access, store, "U_bob") is False


def test_user_allowed_dynamic_approval(tmp_path):
    store = LocalApprovalStore(tmp_path / "approvals.json")
    store.approve("U_dynamic")
    access = ConnectorAccess()
    assert user_allowed(access, store, "U_dynamic") is True


def test_user_not_allowed_when_empty_and_not_approved(tmp_path):
    store = LocalApprovalStore(tmp_path / "approvals.json")
    access = ConnectorAccess()
    assert user_allowed(access, store, "U_unknown") is False
