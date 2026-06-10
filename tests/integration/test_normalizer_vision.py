"""normalizer first-pass image extraction + strip (vision-as-tool D3).

An inbound message carrying image attachments is, before the agent loop runs:
saved to uploads, analyzed once (user text as instruction), the extracted text
injected, and the image stripped to a disk reference — so the history handed to
run() carries no image_url block and the loop routes to the text model.
"""

from unittest.mock import AsyncMock

import yaml

import fleetent.agent_config as agent_config
import fleetent.tools.builtin_tools as tl
import fleetent.user_store as user_store
from fleetent.im_gateway import access, normalizer
from fleetent.tools.multimodal import has_image_block
from tests.integration._migration_template import apply_migrations

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload" * 4


def _bind_default_agent(tmp_path, monkeypatch):
    """Bind a default agent that allows user 'u1' so the per-agent gate passes."""
    root = tmp_path / "agents"
    d = root / "vision-bot"
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": "vision-bot",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
        "bindings": {"default": True},
        "access": {"allow_users": ["u1"]},
    }
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    agent_config.scan(root)
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")


def _setup_db(tmp_path, monkeypatch):

    db_path = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", db_path)
    # normalizer routing queries agent_store, which runs on the unified db runtime.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)


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
    _bind_default_agent(tmp_path, monkeypatch)
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

    import fleetent.runtime.loop as agent_loop

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
    _bind_default_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")

    analyze = AsyncMock()
    monkeypatch.setattr(tl.vision_client, "analyze", analyze)

    captured_messages = {}

    async def fake_run(messages, **kwargs):
        captured_messages["messages"] = list(messages)
        return "done"

    import fleetent.runtime.loop as agent_loop

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
    _bind_default_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")

    async def fake_analyze(image_bytes, instruction, *, settings=None):
        return "first look"

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)

    captured_messages = {}

    async def fake_run(messages, **kwargs):
        captured_messages["messages"] = list(messages)
        return "done"

    import fleetent.runtime.loop as agent_loop

    monkeypatch.setattr(agent_loop, "run", fake_run)

    replies = []
    await normalizer.route(_msg(replies, attachments=[(PNG_BYTES, "image/png")]))

    written = list((tmp_path / "up").glob("*"))
    ref = str(written[0])
    # the model can re-read the same reference later
    assert tl._read_upload(ref) == PNG_BYTES
