"""Tests for Slack-side generated image upload: _extract_generated_image_paths and
upload_func wiring in route(), plus the Slack adapter upload_func implementation."""

from __future__ import annotations

from unittest.mock import MagicMock

# ── _extract_generated_image_paths ────────────────────────────────────────────


def test_finds_path_in_tool_message(tmp_path):
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")

    from fleetent.im_gateway.normalizer import _extract_generated_image_paths

    msgs = [{"role": "tool", "content": f"image generated: {img}", "tool_call_id": "c1"}]
    result = _extract_generated_image_paths(msgs)
    assert result == [str(img)]


def test_skips_missing_file():
    from fleetent.im_gateway.normalizer import _extract_generated_image_paths

    msgs = [{"role": "tool", "content": "image generated: /nonexistent/img.png"}]
    assert _extract_generated_image_paths(msgs) == []


def test_ignores_non_tool_messages(tmp_path):
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")

    from fleetent.im_gateway.normalizer import _extract_generated_image_paths

    msgs = [
        {"role": "assistant", "content": f"image generated: {img}"},
        {"role": "user", "content": f"image generated: {img}"},
    ]
    assert _extract_generated_image_paths(msgs) == []


def test_only_scans_provided_messages(tmp_path):
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")

    from fleetent.im_gateway.normalizer import _extract_generated_image_paths

    # Passing only the tool message; function must not access any global state
    msgs = [{"role": "tool", "content": f"image generated: {img}"}]
    result = _extract_generated_image_paths(msgs)
    assert result == [str(img)]


def test_multiple_images_extracted(tmp_path):
    imgs = [tmp_path / f"img{i}.png" for i in range(3)]
    for img in imgs:
        img.write_bytes(b"PNG")

    from fleetent.im_gateway.normalizer import _extract_generated_image_paths

    msgs = [{"role": "tool", "content": f"image generated: {img}"} for img in imgs]
    result = _extract_generated_image_paths(msgs)
    assert result == [str(img) for img in imgs]


# ── route() upload_func integration ───────────────────────────────────────────


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
                    "access": {
                        "allow_all_users": True,
                        "require_approval": False,
                    },
                }
            },
        }
    )


async def _run_route_with_mock_loop(monkeypatch, tmp_path, upload_func, generated_image=True):
    """Helper: run route() with a mock loop that optionally appends a generate_image tool result."""
    import fleetent.agent_config as ac
    import fleetent.im_gateway.normalizer as norm
    from fleetent.im_gateway.normalizer import NormalizedMessage

    agent = _make_agent_file()
    index = MagicMock()
    index.get.return_value = agent
    index.default_agent.return_value = agent.name
    monkeypatch.setattr(ac, "_index", index)

    img_path = None
    if generated_image:
        img_path = tmp_path / "gen.png"
        img_path.write_bytes(b"PNG")

    async def fake_loop_run(messages, **kwargs):
        reply_func = kwargs.get("reply_func")
        if generated_image:
            messages.append(
                {"role": "tool", "content": f"image generated: {img_path}", "tool_call_id": "c1"}
            )
        if reply_func:
            await reply_func("图片已生成！")
        return "图片已生成！"

    monkeypatch.setattr("fleetent.runtime.loop.run", fake_loop_run)

    replies = []

    async def reply_func(text: str) -> None:
        replies.append(text)

    msg = NormalizedMessage(
        platform="slack",
        session_id="user:U123",
        user_id="U123",
        text="帮我生成一张图",
        attachments=[],
        reply_func=reply_func,
        channel_id="D123",
        agent_name=agent.name,
        upload_func=upload_func,
    )
    await norm.route(msg)
    return img_path, replies


async def test_route_calls_upload_func_with_generated_image(monkeypatch, tmp_path):
    uploaded: list[list[str]] = []

    async def upload_func(paths: list[str]) -> None:
        uploaded.append(paths)

    img_path, _ = await _run_route_with_mock_loop(monkeypatch, tmp_path, upload_func)
    assert len(uploaded) == 1
    assert uploaded[0] == [str(img_path)]


async def test_route_skips_upload_when_upload_func_none(monkeypatch, tmp_path):
    # Should complete without error when upload_func is None
    _, replies = await _run_route_with_mock_loop(monkeypatch, tmp_path, upload_func=None)
    assert replies  # text reply still sent


async def test_route_only_uploads_current_turn_images(monkeypatch, tmp_path):
    """upload_func should NOT be called when the current turn produced no images."""
    uploaded: list[list[str]] = []

    async def upload_func(paths: list[str]) -> None:
        uploaded.append(paths)

    await _run_route_with_mock_loop(monkeypatch, tmp_path, upload_func, generated_image=False)
    assert uploaded == []


# ── Slack upload_func implementation ─────────────────────────────────────────


async def test_slack_upload_func_calls_files_upload_v2(tmp_path):
    img = tmp_path / "img.png"
    img.write_bytes(b"PNG")

    from fleetent.im_gateway import slack as slack_mod

    calls: list[dict] = []

    client = MagicMock()

    async def fake_upload(**kwargs):
        calls.append(kwargs)

    client.files_upload_v2 = fake_upload

    upload_func = slack_mod._make_upload_func(
        client=client, channel="C123", reply_thread="1234.5678"
    )
    await upload_func([str(img)])

    assert len(calls) == 1
    assert calls[0]["channel"] == "C123"
    assert calls[0]["thread_ts"] == "1234.5678"
    assert calls[0]["file"] == str(img)


async def test_slack_upload_func_skips_on_exception(tmp_path):
    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.png"
    img1.write_bytes(b"PNG")
    img2.write_bytes(b"PNG")

    from fleetent.im_gateway import slack as slack_mod

    calls: list[str] = []
    client = MagicMock()

    async def fake_upload(**kwargs):
        path = kwargs["file"]
        if "img1" in path:
            raise RuntimeError("upload failed")
        calls.append(path)

    client.files_upload_v2 = fake_upload

    upload_func = slack_mod._make_upload_func(
        client=client, channel="C123", reply_thread="1234.5678"
    )

    # Must not raise even though img1 fails
    await upload_func([str(img1), str(img2)])

    # img2 was still uploaded despite img1 failing
    assert str(img2) in calls
    # img1 was not uploaded
    assert str(img1) not in calls
