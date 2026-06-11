"""Integration: inbound image lands in per-session workspace uploads/ (vision-as-tool).

A normalized inbound message carrying an image is saved into the per-session
workspace `uploads/`, the main context carries a workspace-relative ref (no base64 /
host-absolute path), and analyze_image reads the same file back via that ref. Vision
endpoint + agent loop are mocked; tmp workspace + db. No docker.
"""


import yaml

import fleetent.agent_config as agent_config
import fleetent.tools.builtin_tools as tl
from fleetent.im_gateway import access, normalizer
from fleetent.tools.multimodal import has_image_block
from fleetent.tools.registry import ToolContext
from tests.integration._migration_template import apply_migrations

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload" * 8


def _bind_default_agent(tmp_path, monkeypatch):
    d = tmp_path / "agents" / "default"
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": "default",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
        "connectors": {
            "slack": {
                "bot_token_env": "TEST_BOT_TOKEN",
                "app_token_env": "TEST_APP_TOKEN",
                "access": {"allow_users": ["u1"]},
            }
        },
    }
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    agent_config.scan()
    monkeypatch.setattr(access, "APPROVALS_PATH", tmp_path / "data" / "im_approvals.json")


def _setup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)


def _msg(replies, attachments):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id="thread:img-ws",
        user_id="u1",
        text="what is in this picture?",
        attachments=attachments,
        reply_func=reply_func,
        channel_id="",
        workspace_id="",
    )


async def test_inbound_image_in_workspace_and_readback(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _bind_default_agent(tmp_path, monkeypatch)

    from fleetent import paths

    ws = tmp_path / "workspaces"
    monkeypatch.setattr(paths, "workspaces_dir", lambda: ws)

    async def fake_analyze(image_bytes, instruction, *, settings=None):
        return "a red square"

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)

    captured = {}

    async def fake_run(messages, **kwargs):
        captured["messages"] = list(messages)
        return "done"

    import fleetent.runtime.loop as agent_loop

    monkeypatch.setattr(agent_loop, "run", fake_run)

    await normalizer.route(_msg([], attachments=[(PNG_BYTES, "image/png")]))

    # image written under per-session workspace uploads/
    written = [p for p in ws.rglob("uploads/*") if p.is_file()]
    assert len(written) == 1
    assert written[0].read_bytes() == PNG_BYTES

    # main context carries the workspace-relative ref, no base64, no host-absolute path
    msgs = captured["messages"]
    assert not has_image_block(msgs)
    blob = repr(msgs)
    import base64

    assert base64.b64encode(PNG_BYTES).decode("ascii") not in blob
    assert f"uploads/{written[0].name}" in blob
    assert str(written[0]) not in blob  # the host-absolute path does not leak

    # analyze_image reads the same physical file back via the workspace ref
    ctx = ToolContext(session_id="thread:img-ws", agent_name=None)
    result = await tl.analyze_image(
        ref=f"uploads/{written[0].name}", instruction="describe", tool_context=ctx
    )
    assert "a red square" in result
