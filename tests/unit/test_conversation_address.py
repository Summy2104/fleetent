"""Unit: ConversationAddress data class + cron origin convergence (conversation-address)."""

from __future__ import annotations

import dataclasses

import pytest

from fleetent.outbound import ConversationAddress


def test_construct_and_frozen():
    addr = ConversationAddress(
        platform="slack",
        chat_id="C123",
        target_type="channel",
        thread_id="170.5",
        user_id="U1",
    )
    assert addr.platform == "slack"
    assert addr.chat_id == "C123"
    assert addr.target_type == "channel"
    assert addr.thread_id == "170.5"
    assert addr.user_id == "U1"
    with pytest.raises(dataclasses.FrozenInstanceError):
        addr.platform = "telegram"  # type: ignore[misc]


def test_dict_roundtrip():
    addr = ConversationAddress(
        platform="slack",
        chat_id="C123",
        target_type="channel",
        thread_id="170.5",
        user_id="U1",
        chat_type="channel",
        thread_root="170.5",
    )
    restored = ConversationAddress.from_dict(addr.to_dict())
    assert restored == addr


def test_from_dict_tolerates_missing_optional_fields():
    restored = ConversationAddress.from_dict({"platform": "slack", "chat_id": "C9"})
    assert restored.platform == "slack"
    assert restored.chat_id == "C9"
    assert restored.target_type == "user"
    assert restored.thread_id is None


def test_from_cron_origin_maps_fields():
    addr = ConversationAddress.from_cron_origin(
        {"platform": "slack", "chat_id": "C7", "target_type": "channel", "thread_id": "12.3"}
    )
    assert addr.platform == "slack"
    assert addr.chat_id == "C7"
    assert addr.target_type == "channel"
    assert addr.thread_id == "12.3"


def test_cron_resolve_delivery_origin_behavior_unchanged():
    from fleetent.cron_scheduler import _resolve_delivery

    task = {
        "origin": {
            "platform": "slack",
            "chat_id": "C7",
            "target_type": "channel",
            "thread_id": "12.3",
        }
    }
    assert _resolve_delivery(task) == ("slack", "C7", "channel", "12.3")


def test_cron_resolve_delivery_explicit_mode_unchanged():
    from fleetent.cron_scheduler import _resolve_delivery

    task = {"deliver": {"mode": "explicit", "platform": "telegram", "target": "999"}}
    assert _resolve_delivery(task) == ("telegram", "999", "user", None)


# ── factories ──────────────────────────────────────────────────────────────


async def test_make_replier_threads_and_passes_blocks(monkeypatch):
    from fleetent import outbound

    calls: list[dict] = []

    async def fake_send_to(platform, connector, target, text, **kw):
        calls.append({"platform": platform, "target": target, "text": text, **kw})
        return True

    monkeypatch.setattr(outbound, "send_to", fake_send_to)
    client = object()
    addr = ConversationAddress(
        platform="slack", chat_id="C1", target_type="channel", thread_id="170.5"
    )
    reply = outbound.make_replier({"slack": client}, addr)
    await reply("hello", blocks=[{"type": "section"}])

    assert calls[0]["platform"] == "slack"
    assert calls[0]["target"] == "C1"
    assert calls[0]["text"] == "hello"
    assert calls[0]["target_type"] == "channel"
    assert calls[0]["thread"] == "170.5"
    assert calls[0]["blocks"] == [{"type": "section"}]


async def test_make_uploader_delivers_each_path_to_thread(monkeypatch):
    from fleetent import outbound

    calls: list[dict] = []

    async def fake_send_file_to(platform, connector, target, path, **kw):
        calls.append({"platform": platform, "target": target, "path": path, **kw})
        return True

    monkeypatch.setattr(outbound, "send_file_to", fake_send_file_to)
    addr = ConversationAddress(
        platform="slack", chat_id="C1", target_type="channel", thread_id="170.5"
    )
    upload = outbound.make_uploader({"slack": object()}, addr)
    await upload(["/a.pdf", "/b.png"])

    assert [c["path"] for c in calls] == ["/a.pdf", "/b.png"]
    assert all(c["thread"] == "170.5" and c["target"] == "C1" for c in calls)


async def test_make_replier_telegram_dispatches_without_platform_branch(monkeypatch):
    from fleetent import outbound

    seen: list[str] = []

    async def fake_send_to(platform, connector, target, text, **kw):
        seen.append(platform)
        return True

    monkeypatch.setattr(outbound, "send_to", fake_send_to)
    addr = ConversationAddress(platform="telegram", chat_id="999", target_type="user")
    reply = outbound.make_replier({"telegram": object()}, addr)
    await reply("hi")

    assert seen == ["telegram"]


async def test_make_replier_missing_connector_is_noop(monkeypatch):
    from fleetent import outbound

    called = []
    monkeypatch.setattr(
        outbound, "send_to", lambda *a, **k: called.append(1)
    )  # would raise if awaited
    addr = ConversationAddress(platform="slack", chat_id="C1")
    reply = outbound.make_replier({}, addr)  # no slack connector
    await reply("hi")  # must not raise, must not dispatch

    assert called == []
