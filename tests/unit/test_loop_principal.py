"""Tests for loop.run / loop.run_stream accepting Principal (tasks 4.1, 5.3).

After task 5.3 the transitional user_id= parameter is removed.
Only principal= is accepted; None defaults to user_id="default".
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch


_MESSAGES = [{"role": "user", "content": "hello"}]


def test_run_accepts_principal_forwards_user_id():
    """run(principal=Principal(...)) must pass principal.user_id to _run_inner as user_id."""
    from fleetent.identity import Principal
    from fleetent.runtime import loop

    captured: dict = {}

    async def _spy(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return "ok"

    with patch.object(loop, "_run_inner", side_effect=_spy):
        asyncio.run(loop.run(_MESSAGES, principal=Principal(user_id="u1", tenant_id="t1")))

    assert captured["user_id"] == "u1"


def test_run_default_is_default():
    """run() with no principal defaults to user_id='default'."""
    from fleetent.runtime import loop

    captured: dict = {}

    async def _spy(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return "ok"

    with patch.object(loop, "_run_inner", side_effect=_spy):
        asyncio.run(loop.run(_MESSAGES))

    assert captured["user_id"] == "default"


def test_run_stream_accepts_principal_no_typeerror():
    """run_stream accepts principal= kwarg without TypeError."""
    from fleetent.identity import Principal
    from fleetent.runtime.loop import run_stream

    gen = run_stream("hi", principal=Principal("u2", "default"))
    asyncio.run(gen.aclose())


def test_run_stream_none_principal_no_typeerror():
    """run_stream with no principal must not raise TypeError."""
    from fleetent.runtime.loop import run_stream

    gen = run_stream("hi")
    asyncio.run(gen.aclose())
