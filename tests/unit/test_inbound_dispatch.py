from __future__ import annotations

from fleetent.im_gateway import inbound_dispatch
from fleetent.im_gateway.normalizer import NormalizedMessage


async def test_inbound_dispatch_routes_to_local_normalizer(monkeypatch) -> None:
    captured = {}

    async def fake_route(msg: NormalizedMessage) -> None:
        captured["msg"] = msg
        await msg.reply_func("standalone reply")

    replies: list[str] = []

    async def fake_reply(text: str) -> None:
        replies.append(text)

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    msg = NormalizedMessage(
        platform="telegram",
        session_id="session-1",
        user_id="u-1",
        text="hello",
        attachments=[],
        reply_func=fake_reply,
    )

    await inbound_dispatch.dispatch(msg)

    assert captured["msg"] is msg
    assert replies == ["standalone reply"]
