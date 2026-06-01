"""Tests for the cancel-token primitive (AR19)."""

from __future__ import annotations

import time

from fleetent.cancellation import CancellationChecker, CancelToken
from fleetent.termination import StopReason


def test_default_token_never_cancelled():
    token = CancelToken()
    assert token.is_cancelled() is False


def test_cancel_marks_cancelled():
    token = CancelToken()
    token.cancel()
    assert token.is_cancelled() is True


def test_cancel_is_idempotent():
    token = CancelToken()
    token.cancel()
    token.cancel()
    assert token.is_cancelled() is True


def test_deadline_not_passed_is_not_cancelled():
    token = CancelToken(deadline=time.monotonic() + 100)
    assert token.is_cancelled() is False


def test_deadline_passed_is_cancelled():
    token = CancelToken(deadline=time.monotonic() - 1)
    assert token.is_cancelled() is True


def test_explicit_cancel_overrides_future_deadline():
    token = CancelToken(deadline=time.monotonic() + 100)
    assert token.is_cancelled() is False
    token.cancel()
    assert token.is_cancelled() is True


# ── CancellationChecker (AR1 framework integration) ──────────────────────────


def test_checker_returns_cancelled_when_token_cancelled():
    token = CancelToken()
    token.cancel()
    checker = CancellationChecker(token)
    from fleetent.termination import LoopState

    assert checker.check(LoopState()) is StopReason.cancelled


def test_checker_returns_none_when_token_live():
    token = CancelToken()
    checker = CancellationChecker(token)
    from fleetent.termination import LoopState

    assert checker.check(LoopState()) is None


# ── parent linkage (AR20 incremental add to AR19) ────────────────────────────


def test_parent_cancel_propagates_to_child():
    parent = CancelToken()
    child = CancelToken(deadline=time.monotonic() + 100, parent=parent)
    assert child.is_cancelled() is False
    parent.cancel()
    assert child.is_cancelled() is True


def test_parent_none_default_preserves_existing_semantics():
    # No parent: behaves exactly as before (own _cancelled / own deadline only).
    token = CancelToken()
    assert token.is_cancelled() is False
    token.cancel()
    assert token.is_cancelled() is True


def test_child_own_deadline_independent_of_live_parent():
    parent = CancelToken()  # never cancelled
    child = CancelToken(deadline=time.monotonic() - 1, parent=parent)  # own deadline passed
    assert child.is_cancelled() is True


def test_live_parent_does_not_cancel_live_child():
    parent = CancelToken()
    child = CancelToken(parent=parent)
    assert child.is_cancelled() is False
