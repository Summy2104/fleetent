"""Unit tests: externalize/rehydrate wired into session save/load round-trip."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

_BIG = "y" * (60 * 1024)  # 60KB, over 50KB limit
_SMALL = "small tool output"


async def test_load_rehydrates_externalized_content(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    # Hand-build an externalized session: JSON holds a reference, external file holds content
    out_dir = tmp_path / "rt.tool_outputs"
    out_dir.mkdir()
    (out_dir / "call-9.txt").write_text(_BIG, encoding="utf-8")
    (tmp_path / "rt.json").write_text(
        json.dumps(
            {
                "meta": {},
                "messages": [
                    {"role": "tool", "tool_call_id": "call-9", "content": "[stored:call-9.txt]"}
                ],
            }
        )
    )

    loaded = await mgr.load("rt")

    assert loaded[0]["content"] == _BIG  # rehydrated to full content


async def test_save_externalizes_large_tool_result(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_last_cleanup_at", __import__("time").time())  # gate closed
    messages = [{"role": "tool", "tool_call_id": "c-save", "content": _BIG}]

    with patch("fleetent.session.index.record_activity"):
        await mgr.save("sv", messages)

    # On-disk JSON holds a reference, not the inline content
    on_disk = json.loads((tmp_path / "sv.json").read_text())
    assert on_disk["messages"][0]["content"] == "[stored:c-save.txt]"
    # External file holds the real content
    assert (tmp_path / "sv.tool_outputs" / "c-save.txt").read_text() == _BIG
    # Input list not mutated
    assert messages[0]["content"] == _BIG


async def test_save_small_tool_result_stays_inline(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_last_cleanup_at", __import__("time").time())
    messages = [{"role": "tool", "tool_call_id": "c-sm", "content": _SMALL}]

    with patch("fleetent.session.index.record_activity"):
        await mgr.save("sv-sm", messages)

    on_disk = json.loads((tmp_path / "sv-sm.json").read_text())
    assert on_disk["messages"][0]["content"] == _SMALL
    assert not (tmp_path / "sv-sm.tool_outputs").exists()


async def test_save_load_round_trip_large_result(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_last_cleanup_at", __import__("time").time())
    messages = [
        {"role": "user", "content": "run it"},
        {"role": "tool", "tool_call_id": "rt-1", "content": _BIG},
    ]

    with patch("fleetent.session.index.record_activity"):
        await mgr.save("roundtrip", messages)
    loaded = await mgr.load("roundtrip")

    assert loaded[1]["content"] == _BIG  # full content recovered after round-trip
    assert loaded[0]["content"] == "run it"
