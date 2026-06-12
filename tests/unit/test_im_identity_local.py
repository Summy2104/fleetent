"""IM user identity resolved locally — no platform user_store on the runtime path."""

from unittest.mock import AsyncMock, MagicMock, patch

import fleetent.im_gateway.slack as slack
from fleetent.im_gateway.access import resolve_identity


def test_resolve_identity_returns_native_id():
    # The agent runtime uses the platform-native id directly as a stable identity.
    assert resolve_identity("slack", "U_alice") == "U_alice"
    assert resolve_identity("telegram", "12345") == "12345"


def test_resolve_identity_uses_injected_resolver_and_resets_to_passthrough():
    from fleetent.im_gateway import access

    access.set_im_identity_resolver(
        lambda owner_id, platform, platform_user_id: (
            f"{owner_id}:{platform}:{platform_user_id}:internal"
        )
    )
    assert access.resolve_identity("slack", "U_alice") == "default:slack:U_alice:internal"

    access.set_im_identity_resolver(None)
    assert access.resolve_identity("slack", "U_alice") == "U_alice"


def test_resolve_identity_and_principal_pass_owner_id_to_resolver():
    from fleetent.im_gateway import access

    calls: list[tuple[str, str, str]] = []

    def _resolver(owner_id: str, platform: str, platform_user_id: str) -> str:
        calls.append((owner_id, platform, platform_user_id))
        return f"mapped:{owner_id}:{platform_user_id}"

    access.set_im_identity_resolver(_resolver)

    assert access.resolve_identity("slack", "U_alice") == "mapped:default:U_alice"
    principal = access.resolve_principal("slack", "U_bob", tenant_id="acme", owner_id="connector-7")
    assert principal.user_id == "mapped:connector-7:U_bob"
    assert principal.tenant_id == "acme"
    assert calls == [
        ("default", "slack", "U_alice"),
        ("connector-7", "slack", "U_bob"),
    ]

    access.set_im_identity_resolver(None)


def _boom(*args, **kwargs):
    raise AssertionError("platform user_store must not be read on the runtime path")


def _build_slack_handler(monkeypatch, agent_name, config):
    routed = {}

    async def fake_route(msg):
        routed["msg"] = msg

    # Rig the platform identity store to raise on any access.
    monkeypatch.setattr("fleetent.platform.im_gateway_management.get_or_create", _boom)
    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    holder = {}
    app = MagicMock()

    def event_deco(name):
        def wrap(fn):
            holder[name] = fn
            return fn

        return wrap

    app.event = event_deco
    with patch("slack_bolt.async_app.AsyncApp", return_value=app):
        slack.create_app(agent_name, config)
    return holder["app_mention"], routed


async def _say(text, thread_ts=None):
    pass


async def test_slack_handler_resolves_identity_without_platform_db(monkeypatch):
    fn, routed = _build_slack_handler(monkeypatch, "support", {"bot_token": "b", "app_token": "a"})
    # Must not raise (no platform user_store read) and must use the native slack id.
    await fn({"user": "U_native", "text": "hi", "ts": "1", "channel": "C1"}, _say)
    assert routed["msg"].user_id == "U_native"


async def test_slack_handler_passes_agent_name_as_owner_id(monkeypatch):
    fn, _ = _build_slack_handler(monkeypatch, "support", {"bot_token": "b", "app_token": "a"})
    calls: list[tuple[str, str, str]] = []

    def _resolve(platform: str, platform_user_id: str, owner_id: str = "default") -> str:
        calls.append((platform, platform_user_id, owner_id))
        return f"mapped:{owner_id}:{platform_user_id}"

    monkeypatch.setattr("fleetent.im_gateway.access.resolve_identity", _resolve)

    await fn({"user": "U_native", "text": "hi", "ts": "1", "channel": "C1"}, _say)

    assert calls == [("slack", "U_native", "support")]


async def test_slack_assistant_route_passes_agent_name_as_owner_id(monkeypatch):
    import fleetent.im_gateway.slack as slack_mod

    calls: list[tuple[str, str, str]] = []
    routed = {}

    def _resolve(platform: str, platform_user_id: str, owner_id: str = "default") -> str:
        calls.append((platform, platform_user_id, owner_id))
        return f"mapped:{owner_id}:{platform_user_id}"

    async def _route(msg):
        routed["msg"] = msg

    async def _set_status(*args, **kwargs):
        return None

    async def _say(*args, **kwargs):
        return None

    monkeypatch.setattr("fleetent.im_gateway.access.resolve_identity", _resolve)
    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", _route)
    monkeypatch.setattr(slack_mod, "_download_attachments", AsyncMock(return_value=[]))

    class _Context:
        channel_id = "D1"
        thread_ts = "171.5"
        user_id = "U_native"

    await slack_mod._route_assistant_message(
        payload={"user": "U_native", "text": "hi", "ts": "171.5"},
        context=_Context(),
        set_status=_set_status,
        say=_say,
        client=MagicMock(),
        agent_name="support",
        bot_token="xoxb-test",
    )

    assert calls == [("slack", "U_native", "support")]
    assert routed["msg"].user_id == "mapped:support:U_native"


async def test_telegram_handler_resolves_identity_without_platform_db(monkeypatch):
    import fleetent.im_gateway.telegram as telegram

    routed = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.platform.im_gateway_management.get_or_create", _boom)
    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    captured = {}

    class FakeApp:
        def add_handler(self, handler):
            captured["handler"] = handler

    class FakeBuilder:
        def token(self, t):
            return self

        def concurrent_updates(self, v):
            return self

        def build(self):
            return FakeApp()

    with patch("telegram.ext.Application") as app_cls:
        app_cls.builder.return_value = FakeBuilder()
        telegram.create_app("support", {"bot_token": "b"})

    handler = captured["handler"]
    fn = handler.callback

    # Build a minimal Update-like object.
    msg_text = MagicMock()
    msg_text.caption = None
    msg_text.text = "hi"
    msg_text.reply_to_message = None
    msg_text.chat.type = "private"
    msg_text.chat.id = 999
    msg_text.photo = None

    update = MagicMock()
    update.message = msg_text
    update.effective_user.id = 424242

    with patch("telegram.Update", MagicMock):
        await fn(update, MagicMock())

    assert routed["msg"].user_id == "424242"


async def test_telegram_handler_passes_agent_name_as_owner_id(monkeypatch):
    import fleetent.im_gateway.telegram as telegram

    routed = {}

    async def fake_route(msg):
        routed["msg"] = msg

    calls: list[tuple[str, str, str]] = []

    def _resolve(platform: str, platform_user_id: str, owner_id: str = "default") -> str:
        calls.append((platform, platform_user_id, owner_id))
        return f"mapped:{owner_id}:{platform_user_id}"

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr("fleetent.im_gateway.access.resolve_identity", _resolve)

    captured = {}

    class FakeApp:
        def add_handler(self, handler):
            captured["handler"] = handler

    class FakeBuilder:
        def token(self, t):
            return self

        def concurrent_updates(self, v):
            return self

        def build(self):
            return FakeApp()

    with patch("telegram.ext.Application") as app_cls:
        app_cls.builder.return_value = FakeBuilder()
        telegram.create_app("support", {"bot_token": "b"})

    handler = captured["handler"]
    fn = handler.callback

    msg_text = MagicMock()
    msg_text.caption = None
    msg_text.text = "hi"
    msg_text.reply_to_message = None
    msg_text.chat.type = "private"
    msg_text.chat.id = 999
    msg_text.photo = None

    update = MagicMock()
    update.message = msg_text
    update.effective_user.id = 424242
    update.effective_user.full_name = "Alice"

    with patch("telegram.Update", MagicMock):
        await fn(update, MagicMock())

    assert calls == [("telegram", "424242", "support")]
    assert routed["msg"].user_id == "mapped:support:424242"
