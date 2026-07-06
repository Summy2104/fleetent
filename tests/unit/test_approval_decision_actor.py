"""Unit: approval decision actor resolves through the same identity seam as inbound.

The permission gate records authorized actors as the run's principal.user_id — under managed
identity resolution that is the internal user id. Approval button/command handlers must
resolve the acting user's platform id through the same seam so the authz check compares
like-for-like. Standalone (no resolver) is a no-op passthrough. (AAA-8266)
"""

from __future__ import annotations

import pytest

from fleetent.im_gateway import access


@pytest.fixture(autouse=True)
def _reset_resolver():
    access.set_im_identity_resolver(None)
    yield
    access.set_im_identity_resolver(None)


def test_managed_resolves_platform_id_to_internal(monkeypatch):
    # Injected resolver = managed: (owner_id, platform, platform_user_id) -> internal user id.
    access.set_im_identity_resolver(lambda owner, platform, pid: "uuid-x" if pid == "U123" else pid)
    assert access.resolve_decision_actor("slack", "U123", "bi-intern") == "uuid-x"


def test_standalone_passthrough_when_no_resolver():
    # No resolver injected (standalone) → raw platform id unchanged.
    assert access.resolve_decision_actor("slack", "U123", "default") == "U123"


def test_non_real_id_fails_closed():
    # Empty / non-real id → None (caller rejects the decision; never authorizes a ghost).
    assert access.resolve_decision_actor("slack", "", "default") is None
    assert access.resolve_decision_actor("telegram", "unknown", "default") is None
