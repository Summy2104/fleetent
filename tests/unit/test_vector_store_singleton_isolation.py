"""Regression: the vector_store module-level singletons must not leak across tests.

A unit test that calls ``configure_from_active_agent()`` (or otherwise sets the
module-level ``_embedding`` / ``_backend``) used to leave a live ``HttpEmbeddingProvider``
pointing at an unreachable agent endpoint. Every later ``loop.run()`` test that
exercised retrieval then made a real HTTP call and blocked on the ~5s connect
timeout — silently inflating the unit suite by ~80s. An autouse conftest fixture
must restore these singletons after each test, mirroring ``_reset_agent_config_index``.

These two tests run in definition order: the first publishes a sentinel, the second
asserts the sentinel did not survive into a later test.
"""

from __future__ import annotations

from fleetent.vector_store import runtime as vrt

_SENTINEL = object()


def test_publishes_embedding_singleton() -> None:
    vrt._embedding = _SENTINEL  # type: ignore[assignment]


def test_embedding_singleton_does_not_leak_into_later_test() -> None:
    assert getattr(vrt, "_embedding", None) is not _SENTINEL
