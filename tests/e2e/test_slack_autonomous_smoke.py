"""E2E smoke for the Slack autonomous helper — real Slack round-trips.

Skipped unless ``SLACK_E2E_TOKEN`` / ``SLACK_E2E_CHANNEL`` / ``SLACK_E2E_BOT_USER_ID``
are set (and a fleetent server is serving the bot in that channel). These exercise the
helper end to end; the driver (skill) judges capabilities — these only prove the pipe.
"""

from __future__ import annotations

import argparse
import base64
import os

import pytest

from tests.e2e.slack_autonomous import helper

_LIVE = bool(
    os.environ.get("SLACK_E2E_TOKEN")
    and os.environ.get("SLACK_E2E_CHANNEL")
    and os.environ.get("SLACK_E2E_BOT_USER_ID")
)
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="needs SLACK_E2E_TOKEN/CHANNEL/BOT_USER_ID + live fleetent server"
)

# 1x1 transparent PNG — a minimal real image for the upload round-trip.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _ns(**kw: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "token": None,
        "channel": None,
        "bot_user_id": None,
        "thread_ts": None,
        "text": None,
        "after_ts": None,
        "timeout": 90.0,
        "poll_interval": 3.0,
        "file": None,
        "title": None,
        "url": None,
        "file_id": None,
        "out": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def test_resolve_send_read_roundtrip() -> None:
    assert helper.cmd_resolve(_ns())["ok"] is True, "preconditions not satisfied"

    sent = helper.cmd_send(_ns(text="[e2e-smoke] ping, 请回我一句"))
    assert sent["ok"], sent

    got = helper.cmd_read(_ns(thread_ts=sent["ts"], after_ts=sent["ts"]))
    assert got["ok"], got
    assert not got["timed_out"] and got["messages"], "no bot reply within timeout"


def test_upload_then_read_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    img = tmp_path / "probe.png"
    img.write_bytes(_PNG_1X1)

    sent = helper.cmd_send(_ns(text="[e2e-smoke] 这张图是什么？"))
    assert sent["ok"], sent
    up = helper.cmd_upload(_ns(file=str(img), thread_ts=sent["ts"], title="probe"))
    assert up["ok"], up

    got = helper.cmd_read(_ns(thread_ts=sent["ts"], after_ts=sent["ts"]))
    assert got["ok"] and got["messages"], "no bot reply to the uploaded image"
