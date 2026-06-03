"""TUI gateway abort: cancel in-flight run + closing notification (tui-gateway 4.3)."""

import asyncio
from typing import Any

from fleetent.tui import dispatch as d


class FakeTransport:
    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    async def write(self, obj: dict[str, Any]) -> bool:
        self.written.append(obj)
        return True

    async def close(self) -> None:
        pass


async def test_abort_cancels_token_and_sends_closing_done(monkeypatch):
    async def fake_run_stream(message, cancel_token=None, **kwargs):
        yield {"type": "text_delta", "content": "working"}
        while cancel_token is not None and not cancel_token.is_cancelled():
            await asyncio.sleep(0.005)
        # cancelled → stop without a terminal event of our own

    monkeypatch.setattr(d, "run_stream", fake_run_stream)
    t = FakeTransport()
    conn = d.Connection(user_id="u1", transport=t)

    resp = await d.dispatch(conn, {"id": 1, "method": "send", "params": {"message": "hi"}})
    run_id = resp["result"]["run_id"]
    await asyncio.sleep(0.02)  # let the run emit its first delta + start waiting
    token = conn.cancel_tokens.get(run_id)
    assert token is not None

    abort_resp = await d.dispatch(conn, {"id": 2, "method": "abort", "params": {"run_id": run_id}})
    assert abort_resp["result"] == {"ok": True, "aborted": True}
    assert token.is_cancelled()

    await asyncio.gather(*list(conn._tasks))
    # a closing `done` with aborted flag was pushed, and the token is cleaned up
    done = [w for w in t.written if w["params"]["type"] == "done"]
    assert done and done[-1]["params"]["payload"].get("aborted") is True
    assert run_id not in conn.cancel_tokens


async def test_abort_unknown_run_id_does_not_crash():
    conn = d.Connection(user_id="u1", transport=FakeTransport())
    resp = await d.dispatch(conn, {"id": 9, "method": "abort", "params": {"run_id": "nope"}})
    assert resp["result"] == {"ok": False, "aborted": False}
