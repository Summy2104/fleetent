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
from fleetent.im_gateway import access, normalizer
from fleetent.tools.multimodal import has_image_block
from tests.integration._migration_template import apply_migrations

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload" * 4


def _bind_default_agent(tmp_path, monkeypatch):
    """Deploy a single home agent allowing 'u1' (bindings were removed from AgentFile;
    the deployed tenant-first default home is the forced default and the IM gate
    lives on the per-platform connector declaration)."""
    d = tmp_path / "tenants" / "default" / "agents" / "default"
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": "default",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
        "im": {
            "supports_dm": True,
            "slack": {
                "bot_token_env": "TEST_BOT_TOKEN",
                "app_token_env": "TEST_APP_TOKEN",
                "access": {"allow_users": ["u1"]},
            },
        },
    }
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    agent_config.scan()
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")


def _setup_db(tmp_path, monkeypatch):

    db_path = tmp_path / "users.db"
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


def _redirect_workspaces(tmp_path, monkeypatch):
    """Point the per-scope workspace root at tmp (uploads now land there, not UPLOADS_DIR)."""
    from fleetent import paths

    ws = tmp_path / "workspaces"
    monkeypatch.setattr(paths, "workspaces_dir", lambda: ws)
    return ws


def _uploaded_files(ws_root):
    """All files written under any per-scope workspace `uploads/` subdir."""
    return [p for p in ws_root.rglob("uploads/*") if p.is_file()]


async def test_image_message_extracted_and_stripped(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _bind_default_agent(tmp_path, monkeypatch)
    ws = _redirect_workspaces(tmp_path, monkeypatch)

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

    # (a) image written to the per-scope workspace uploads/
    written = _uploaded_files(ws)
    assert len(written) == 1
    assert written[0].read_bytes() == PNG_BYTES
    # (b) analyze called once with the image and the user text as instruction
    assert captured["bytes"] == PNG_BYTES
    assert "invoice" in captured["instruction"]
    # (c)+(d) the message handed to run carries the extracted text and a workspace-relative
    # ref, and (e) no image_url block remains → routes default.
    msgs = captured_messages["messages"]
    assert not has_image_block(msgs)
    blob = repr(msgs)
    assert "Total: $42.00" in blob
    assert f"uploads/{written[0].name}" in blob


async def test_no_image_message_unchanged(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _bind_default_agent(tmp_path, monkeypatch)
    ws = _redirect_workspaces(tmp_path, monkeypatch)

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
    assert not _uploaded_files(ws)
    assert captured_messages["messages"][-1]["content"] == "what is the total on this invoice?"


async def test_reference_still_readable_for_followup_analyze(tmp_path, monkeypatch):
    """After strip, the on-disk reference still reads back so the model can call
    analyze_image again (read-on-demand look-back)."""
    _setup_db(tmp_path, monkeypatch)
    _bind_default_agent(tmp_path, monkeypatch)
    ws = _redirect_workspaces(tmp_path, monkeypatch)

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

    written = _uploaded_files(ws)
    # the model can re-read the same reference later via its workspace-relative ref +
    # the originating session's tool context.
    from fleetent.tools.registry import ToolContext

    ctx = ToolContext(session_id="thread:vision", agent_name=None)
    assert tl._read_upload(f"uploads/{written[0].name}", ctx) == PNG_BYTES
