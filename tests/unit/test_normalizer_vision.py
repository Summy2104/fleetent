"""normalizer first-pass image extraction + strip (vision-as-tool D3).

An inbound message carrying image attachments is, before the agent loop runs:
saved to uploads, analyzed once (user text as instruction), the extracted text
injected, and the image stripped to a disk reference — so the history handed to
run() carries no image_url block and the loop routes to the text model.
"""

from unittest.mock import AsyncMock

import fleetent.im_channel_allowlist as acl
import fleetent.im_connector_store as ics
import fleetent.im_user_store as im_user_store
import fleetent.tools as tl
import fleetent.user_store as user_store
from fleetent.im_gateway import normalizer
from fleetent.multimodal import has_image_block

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload" * 4


def _setup_db(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "users.db"
    for mod in (user_store, ics, acl):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    # normalizer routing queries agent_store, which runs on the unified db runtime.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    ics._init_db()
    acl._init_db()


def _msg(replies, attachments):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id="thread:vision",
        user_id="u1",
        text="what is the total on this invoice?",
        attachments=attachments,
        reply_func=reply_func,
        channel_id="",
        workspace_id="",
    )


async def test_image_message_extracted_and_stripped(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", lambda _uid: True)
    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")

    captured = {}

    async def fake_analyze(image_bytes, instruction, *, settings=None):
        captured["bytes"] = image_bytes
        captured["instruction"] = instruction
        return "Total: $42.00"

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)

    captured_messages = {}

    async def fake_run(messages, **kwargs):
        captured_messages["messages"] = list(messages)
        return "done"

    import fleetent.agent_loop as agent_loop

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies = []
    await normalizer.route(_msg(replies, attachments=[(PNG_BYTES, "image/png")]))

    # (a) image written to uploads
    written = list((tmp_path / "up").glob("*"))
    assert len(written) == 1
    assert written[0].read_bytes() == PNG_BYTES
    # (b) analyze called once with the image and the user text as instruction
    assert captured["bytes"] == PNG_BYTES
    assert "invoice" in captured["instruction"]
    # (c)+(d) the message handed to run carries the extracted text and a ref,
    # and (e) no image_url block remains → routes default.
    msgs = captured_messages["messages"]
    assert not has_image_block(msgs)
    blob = repr(msgs)
    assert "Total: $42.00" in blob
    assert str(written[0]) in blob


async def test_no_image_message_unchanged(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", lambda _uid: True)
    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")

    analyze = AsyncMock()
    monkeypatch.setattr(tl.vision_client, "analyze", analyze)

    captured_messages = {}

    async def fake_run(messages, **kwargs):
        captured_messages["messages"] = list(messages)
        return "done"

    import fleetent.agent_loop as agent_loop

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies = []
    await normalizer.route(_msg(replies, attachments=[]))

    # plain text path: no vision call, no uploads, last message is the user text
    analyze.assert_not_awaited()
    assert not (tmp_path / "up").exists() or not list((tmp_path / "up").glob("*"))
    assert captured_messages["messages"][-1]["content"] == "what is the total on this invoice?"


async def test_reference_still_readable_for_followup_analyze(tmp_path, monkeypatch):
    """After strip, the on-disk reference still reads back so the model can call
    analyze_image again (read-on-demand look-back)."""
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(im_user_store, "check_allowed_by_user_id", lambda _uid: True)
    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")

    async def fake_analyze(image_bytes, instruction, *, settings=None):
        return "first look"

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)

    captured_messages = {}

    async def fake_run(messages, **kwargs):
        captured_messages["messages"] = list(messages)
        return "done"

    import fleetent.agent_loop as agent_loop

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies = []
    await normalizer.route(_msg(replies, attachments=[(PNG_BYTES, "image/png")]))

    written = list((tmp_path / "up").glob("*"))
    ref = str(written[0])
    # the model can re-read the same reference later
    assert tl._read_upload(ref) == PNG_BYTES
