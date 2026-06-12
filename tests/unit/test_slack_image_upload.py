"""Tests for the Slack adapter upload_func implementation.

sandbox-file-egress retired the normalizer regex-sniff host auto-reflow (it was
structurally broken for container-written products). The `_extract_generated_image_paths`
host-inference helper and the route() auto-upload it drove are gone; the explicit
egress notice and the send_file tool now own product delivery (covered by
test_normalizer_egress_retired.py and test_send_file.py). The Slack `_make_upload_func`
remains the per-file delivery wrapper used by the unified outbound primitive.
"""

from __future__ import annotations

from unittest.mock import MagicMock


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
