"""Unit tests: IM `approve always <id>` parsing routes to resolve(always=True).

(approval-minimization, task 4)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fleetent.im_gateway import normalizer
from fleetent.im_gateway.normalizer import NormalizedMessage


def _msg(text: str) -> NormalizedMessage:
    return NormalizedMessage(
        platform="slack",
        session_id="s",
        user_id="slack:U_LEAD",
        text=text,
        attachments=[],
        reply_func=AsyncMock(),
    )


@pytest.fixture
def spy_resolve(monkeypatch):
    import fleetent.governance.approval_router as approval_router
    import fleetent.session.manager as session_mgr

    resolve = AsyncMock(return_value=True)
    monkeypatch.setattr(approval_router, "resolve_approval_request", resolve)
    monkeypatch.setattr(session_mgr, "get_pending_approval", AsyncMock(return_value=None))
    return resolve


async def test_approve_always_routes_always_true(spy_resolve) -> None:
    await normalizer.route(_msg("approve always abc12345"))
    assert spy_resolve.await_args.kwargs["always"] is True
    assert spy_resolve.await_args.kwargs["decision"] == "approved"
    assert spy_resolve.await_args.kwargs["approval_id"] == "abc12345"


async def test_plain_approve_routes_always_false(spy_resolve) -> None:
    await normalizer.route(_msg("approve abc12345"))
    assert spy_resolve.await_args.kwargs["always"] is False
    assert spy_resolve.await_args.kwargs["decision"] == "approved"


async def test_reject_routes_rejected(spy_resolve) -> None:
    await normalizer.route(_msg("reject abc12345"))
    assert spy_resolve.await_args.kwargs["decision"] == "rejected"
    assert spy_resolve.await_args.kwargs["always"] is False
