from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import respx


def _capture_slack_handler(monkeypatch):
    """Build the slack app with a fake AsyncApp whose .event() is an identity
    decorator, so we can capture and directly invoke the registered handler."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    captured: dict[str, object] = {}

    class FakeApp:
        def event(self, name: str):  # noqa: ANN201
            def deco(fn):  # noqa: ANN001, ANN202
                captured["handler"] = fn
                return fn

            return deco

    with patch("slack_bolt.async_app.AsyncApp", return_value=FakeApp()):
        import fleetent.im_gateway.slack as slack_mod

        slack_mod.create_app(
            "support", "owner1", {"bot_token": "xoxb-test-token", "app_token": "xapp-test-token"}
        )
    return captured["handler"]


async def _run_slack(handler, event, monkeypatch):
    """Invoke a captured slack handler with route + im_user_store mocked,
    returning the NormalizedMessage handed to route()."""
    import fleetent.im_gateway.normalizer as norm
    import fleetent.im_user_store as ius

    fake_user = MagicMock()
    fake_user.id = "internal-1"
    monkeypatch.setattr(ius, "get_or_create", lambda owner_id, platform, uid: fake_user)
    captured_msg = AsyncMock()
    monkeypatch.setattr(norm, "route", captured_msg)

    say = AsyncMock()
    await handler(event, say)
    captured_msg.assert_called_once()
    return captured_msg.call_args[0][0]


@respx.mock
async def test_slack_image_file_downloaded_into_attachments(monkeypatch):
    handler = _capture_slack_handler(monkeypatch)
    route_obj = respx.get("https://files.slack.com/secret.png").mock(
        return_value=httpx.Response(200, content=b"PNGBYTES")
    )

    event = {
        "user": "U1",
        "text": "look at this",
        "channel_type": "im",
        "ts": "111.0",
        "files": [{"mimetype": "image/png", "url_private": "https://files.slack.com/secret.png"}],
    }
    msg = await _run_slack(handler, event, monkeypatch)

    assert msg.attachments == [(b"PNGBYTES", "image/png")]
    # bot token must be used for url_private auth
    assert route_obj.calls.last.request.headers["Authorization"] == "Bearer xoxb-test-token"


@respx.mock
async def test_slack_non_image_file_ignored(monkeypatch):
    handler = _capture_slack_handler(monkeypatch)
    pdf_route = respx.get("https://files.slack.com/doc.pdf").mock(
        return_value=httpx.Response(200, content=b"PDF")
    )

    event = {
        "user": "U1",
        "text": "doc",
        "channel_type": "im",
        "ts": "111.0",
        "files": [
            {"mimetype": "application/pdf", "url_private": "https://files.slack.com/doc.pdf"}
        ],
    }
    msg = await _run_slack(handler, event, monkeypatch)

    assert msg.attachments == []
    assert not pdf_route.called


async def test_slack_no_files_empty_attachments(monkeypatch):
    handler = _capture_slack_handler(monkeypatch)
    event = {"user": "U1", "text": "plain", "channel_type": "im", "ts": "111.0"}
    msg = await _run_slack(handler, event, monkeypatch)
    assert msg.attachments == []
    assert msg.text == "plain"


@respx.mock
async def test_slack_download_failure_degrades_to_empty(monkeypatch):
    handler = _capture_slack_handler(monkeypatch)
    respx.get("https://files.slack.com/boom.png").mock(
        return_value=httpx.Response(500, content=b"err")
    )

    event = {
        "user": "U1",
        "text": "boom",
        "channel_type": "im",
        "ts": "111.0",
        "files": [{"mimetype": "image/png", "url_private": "https://files.slack.com/boom.png"}],
    }
    # must not raise
    msg = await _run_slack(handler, event, monkeypatch)
    assert msg.attachments == []


# ----------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------


def _capture_telegram_handler(monkeypatch):
    """Build telegram app with mocked Application builder; capture the handler
    callback passed to add_handler and the filters on the MessageHandler."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-test-token")

    mock_app = MagicMock()
    mock_builder = MagicMock()
    mock_builder.token.return_value = mock_builder
    mock_builder.concurrent_updates.return_value = mock_builder
    mock_builder.build.return_value = mock_app

    with patch("telegram.ext.Application") as mock_cls:
        mock_cls.builder.return_value = mock_builder
        import fleetent.im_gateway.telegram as tg_mod

        tg_mod.create_app("support", "owner1", {"bot_token": "tg-test-token"})

    handler_obj = mock_app.add_handler.call_args[0][0]
    return handler_obj


async def _run_telegram(handler_obj, update, context, monkeypatch):
    import fleetent.im_gateway.normalizer as norm
    import fleetent.im_user_store as ius

    fake_user = MagicMock()
    fake_user.id = "internal-tg-1"
    monkeypatch.setattr(ius, "get_or_create", lambda owner_id, platform, uid: fake_user)
    captured = AsyncMock()
    monkeypatch.setattr(norm, "route", captured)

    await handler_obj.callback(update, context)
    captured.assert_called_once()
    return captured.call_args[0][0]


def _telegram_photo_update(*, caption=None, text=None):
    from telegram import Update

    update = MagicMock(spec=Update)
    msg = MagicMock()
    eff_user = MagicMock()
    eff_user.id = 555
    update.effective_user = eff_user
    update.message = msg
    msg.reply_to_message = None
    chat = MagicMock()
    chat.type = "private"
    msg.chat = chat
    msg.caption = caption
    msg.text = text
    # two PhotoSizes: smallest first, largest last
    small = MagicMock()
    small.file_id = "small"
    large = MagicMock()
    large.file_id = "large"
    msg.photo = [small, large]
    return update


def _telegram_context_with_file(byte_data, *, raise_on_get=False):
    context = MagicMock()
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(byte_data))
    if raise_on_get:
        context.bot.get_file = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        context.bot.get_file = AsyncMock(return_value=tg_file)
    return context


async def test_telegram_photo_downloaded_into_attachments(monkeypatch):
    callback = _capture_telegram_handler(monkeypatch)
    update = _telegram_photo_update(caption="invoice", text=None)
    context = _telegram_context_with_file(b"JPEGBYTES")

    msg = await _run_telegram(callback, update, context, monkeypatch)

    assert msg.attachments == [(b"JPEGBYTES", "image/jpeg")]
    # largest PhotoSize selected
    context.bot.get_file.assert_awaited_once_with("large")


async def test_telegram_photo_text_from_caption(monkeypatch):
    callback = _capture_telegram_handler(monkeypatch)
    update = _telegram_photo_update(caption="please read", text=None)
    context = _telegram_context_with_file(b"JPEG")

    msg = await _run_telegram(callback, update, context, monkeypatch)
    assert msg.text == "please read"


async def test_telegram_plain_text_unchanged(monkeypatch):
    callback = _capture_telegram_handler(monkeypatch)
    update = _telegram_photo_update(caption=None, text="hi there")
    update.message.photo = []  # plain text message
    context = MagicMock()

    msg = await _run_telegram(callback, update, context, monkeypatch)
    assert msg.attachments == []
    assert msg.text == "hi there"


async def test_telegram_download_failure_degrades_to_empty(monkeypatch):
    callback = _capture_telegram_handler(monkeypatch)
    update = _telegram_photo_update(caption="x", text=None)
    context = _telegram_context_with_file(b"", raise_on_get=True)

    msg = await _run_telegram(callback, update, context, monkeypatch)
    assert msg.attachments == []


async def test_telegram_handler_filter_accepts_photo(monkeypatch):
    """The registered MessageHandler must accept photo updates, not only text."""
    from telegram.ext import filters

    handler_obj = _capture_telegram_handler(monkeypatch)
    flt = handler_obj.filters
    # Build a photo-only update check: filters must include PHOTO
    repr_str = repr(flt)
    assert "PHOTO" in repr_str or "Photo" in repr_str
    # sanity: filters object exists and is a telegram filter
    assert isinstance(flt, filters.BaseFilter)
