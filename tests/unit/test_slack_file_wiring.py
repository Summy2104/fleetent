"""All three Slack receive paths route inbound non-image files to the agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import fleetent.im_gateway.slack as slack
from fleetent.im_gateway.normalizer import _file_attachments

_SHEET_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self, content: bytes):
        self._content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        return _Resp(self._content)


def _build_handlers(monkeypatch):
    routed: dict = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity", lambda p, uid: uid, raising=False
    )
    handlers: dict = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            handlers[name] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app("my-bot", {"bot_token": "b", "app_token": "a"})
    return handlers, routed


def _xlsx_files():
    return [
        {
            "name": "data.xlsx",
            "mimetype": _SHEET_MIME,
            "url_private": "https://files.slack.com/d.xlsx",
            "size": 10,
        }
    ]


async def _say(text="", thread_ts=None, **kwargs):
    pass


async def test_app_mention_routes_file_attachment(monkeypatch):
    handlers, routed = _build_handlers(monkeypatch)
    event = {"user": "U1", "text": "<@B> 总结", "ts": "1", "channel": "C1", "files": _xlsx_files()}
    with patch("httpx.AsyncClient", return_value=_FakeClient(b"xlsx")):
        await handlers["app_mention"](event, MagicMock(), _say)
    files = _file_attachments(routed["msg"].attachments)
    assert len(files) == 1
    assert files[0].data == b"xlsx"
    assert files[0].filename == "data.xlsx"


async def test_dm_routes_file_attachment(monkeypatch):
    handlers, routed = _build_handlers(monkeypatch)
    event = {
        "user": "U1",
        "text": "总结",
        "ts": "1",
        "channel": "D1",
        "channel_type": "im",
        "files": _xlsx_files(),
    }
    with patch("httpx.AsyncClient", return_value=_FakeClient(b"xlsx")):
        await handlers["message"](event, MagicMock(), _say)
    files = _file_attachments(routed["msg"].attachments)
    assert len(files) == 1
    assert files[0].data == b"xlsx"


async def test_assistant_routes_file_attachment(monkeypatch):
    routed: dict = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity", lambda p, uid: uid, raising=False
    )
    ctx = MagicMock()
    ctx.channel_id = "D1"
    ctx.thread_ts = "1"
    payload = {"user": "U1", "text": "总结", "ts": "1", "files": _xlsx_files()}
    with patch("httpx.AsyncClient", return_value=_FakeClient(b"xlsx")):
        await slack._route_assistant_message(
            payload=payload,
            context=ctx,
            set_status=AsyncMock(),
            say=AsyncMock(),
            client=MagicMock(),
            agent_name="my-bot",
            bot_token="b",
        )
    files = _file_attachments(routed["msg"].attachments)
    assert len(files) == 1
    assert files[0].data == b"xlsx"
