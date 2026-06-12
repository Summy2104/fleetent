"""Unit tests for retiring the regex-sniff auto-reflow (sandbox-file-egress).

route() MUST NOT use host Path.is_file() on container-side paths to auto-upload;
when this turn produced a generative product that cannot be host-located, route()
appends an explicit "use send_file" notice rather than silently dropping it. The
upload_func injection channel stays on NormalizedMessage (contract unchanged).
"""

from __future__ import annotations

from dataclasses import fields
from unittest.mock import MagicMock


def _make_agent_file(name: str = "test-agent"):
    from fleetent.agent_config import AgentFile

    return AgentFile.model_validate(
        {
            "name": name,
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "primary",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://local.test/v1/",
                        "model": "text",
                    }
                ],
                "routes": {"default": [{"target": "primary"}]},
            },
            "connectors": {
                "slack": {
                    "bot_token_env": "SLACK_BOT_TOKEN",
                    "app_token_env": "SLACK_APP_TOKEN",
                    "access": {"allow_all_users": True, "require_approval": False},
                }
            },
        }
    )


async def _run_route(monkeypatch, *, tool_content: str | None, upload_func=None):
    """Run route() with a mock loop that appends one tool result, capturing replies."""
    import fleetent.agent_config as ac
    import fleetent.im_gateway.normalizer as norm
    from fleetent.im_gateway.normalizer import NormalizedMessage

    agent = _make_agent_file()
    index = MagicMock()
    index.get.return_value = agent
    index.default_agent.return_value = agent.name
    monkeypatch.setattr(ac, "_index", index)

    async def fake_loop_run(messages, **kwargs):
        if tool_content is not None:
            messages.append({"role": "tool", "content": tool_content, "tool_call_id": "c1"})
        reply_func = kwargs.get("reply_func")
        if reply_func:
            await reply_func("done")
        return "done"

    monkeypatch.setattr("fleetent.runtime.loop.run", fake_loop_run)

    replies: list[str] = []

    async def reply_func(text: str) -> None:
        replies.append(text)

    msg = NormalizedMessage(
        platform="slack",
        session_id="user:U123",
        user_id="U123",
        text="帮我生成产物",
        attachments=[],
        reply_func=reply_func,
        channel_id="D123",
        agent_name=agent.name,
        upload_func=upload_func,
    )
    await norm.route(msg)
    return replies


def test_upload_func_field_still_exists() -> None:
    from fleetent.im_gateway.normalizer import NormalizedMessage

    names = {f.name for f in fields(NormalizedMessage)}
    assert "upload_func" in names


async def test_container_path_not_auto_uploaded(monkeypatch) -> None:
    """A container-side path in tool output MUST NOT be host-checked and auto-uploaded."""
    uploaded: list[list[str]] = []

    async def upload_func(paths: list[str]) -> None:
        uploaded.append(paths)

    await _run_route(
        monkeypatch,
        tool_content="image generated: generated/out.png",
        upload_func=upload_func,
    )
    assert uploaded == []  # never auto-uploaded


async def test_product_intent_yields_explicit_notice(monkeypatch) -> None:
    """When the turn produced a product but it cannot be auto-delivered, route() must
    surface an explicit "use send_file" notice rather than silently dropping it."""
    replies = await _run_route(monkeypatch, tool_content="image generated: generated/out.png")
    joined = "\n".join(replies)
    assert "send_file" in joined


async def test_no_product_no_notice(monkeypatch) -> None:
    """A turn with no generative product must NOT emit the egress notice."""
    replies = await _run_route(monkeypatch, tool_content="some unrelated tool result")
    joined = "\n".join(replies)
    assert "send_file" not in joined
