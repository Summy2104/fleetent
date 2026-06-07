"""Unit tests: large tool result externalization in session/manager.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

_BIG = "x" * (60 * 1024)  # 60KB, over the 50KB limit
_SMALL = "small result"


# ── externalize_tool_results ──────────────────────────────────────────────────


def test_externalize_large_tool_result(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [
        {"role": "user", "content": "go"},
        {"role": "tool", "tool_call_id": "call-1", "content": _BIG},
    ]

    result = mgr.externalize_tool_results("sess-1", messages)

    ext = tmp_path / "sess-1.tool_outputs" / "call-1.txt"
    assert ext.exists()
    assert ext.read_text() == _BIG
    assert result[1]["content"] == "[stored:call-1.txt]"


def test_externalize_small_tool_result_stays_inline(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "tool", "tool_call_id": "c", "content": _SMALL}]

    result = mgr.externalize_tool_results("sess-2", messages)

    assert result[0]["content"] == _SMALL
    assert not (tmp_path / "sess-2.tool_outputs").exists()


def test_externalize_non_tool_message_untouched(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "assistant", "content": _BIG}]

    result = mgr.externalize_tool_results("sess-3", messages)

    assert result[0]["content"] == _BIG
    assert not (tmp_path / "sess-3.tool_outputs").exists()


def test_externalize_does_not_mutate_input(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "tool", "tool_call_id": "c1", "content": _BIG}]

    mgr.externalize_tool_results("sess-4", messages)

    assert messages[0]["content"] == _BIG  # original unchanged


def test_externalize_slash_session_id(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "tool", "tool_call_id": "c", "content": _BIG}]

    mgr.externalize_tool_results("slack:C1/U2", messages)

    assert (tmp_path / "slack:C1" / "U2.tool_outputs" / "c.txt").exists()


# ── rehydrate_tool_results ────────────────────────────────────────────────────


def test_rehydrate_reads_back_content(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "tool", "tool_call_id": "c1", "content": _BIG}]
    externalized = mgr.externalize_tool_results("sess-r", messages)

    rehydrated = mgr.rehydrate_tool_results("sess-r", externalized)

    assert rehydrated[0]["content"] == _BIG


def test_rehydrate_missing_file_keeps_reference(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "tool", "tool_call_id": "gone", "content": "[stored:gone.txt]"}]

    result = mgr.rehydrate_tool_results("sess-missing", messages)

    assert result[0]["content"] == "[stored:gone.txt]"  # placeholder kept


def test_rehydrate_no_reference_returns_unchanged(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "tool", "tool_call_id": "c", "content": "plain text"}]

    result = mgr.rehydrate_tool_results("sess-plain", messages)

    assert result[0]["content"] == "plain text"


# ── session package exports ───────────────────────────────────────────────────


def test_session_package_exports_extern_functions() -> None:
    from fleetent import session as session_pkg

    assert hasattr(session_pkg, "externalize_tool_results")
    assert hasattr(session_pkg, "rehydrate_tool_results")


# ── cleanup_expired tool_outputs handling ─────────────────────────────────────


def test_cleanup_deletes_tool_outputs_dir(tmp_path: Path, monkeypatch) -> None:
    import os

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    main = tmp_path / "ts.json"
    main.write_text('{"meta":{},"messages":[]}')
    os.utime(main, (0, 0))
    outdir = tmp_path / "ts.tool_outputs"
    outdir.mkdir()
    (outdir / "c.txt").write_text("data")

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert "ts" in removed
    assert not main.exists()
    assert not outdir.exists()  # tool_outputs dir removed


def test_cleanup_skips_files_inside_tool_outputs(tmp_path: Path, monkeypatch) -> None:
    import os

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    outdir = tmp_path / "x.tool_outputs"
    outdir.mkdir()
    stray = outdir / "inner.json"  # a .json inside tool_outputs must not be a session
    stray.write_text("{}")
    os.utime(stray, (0, 0))

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert not any(".tool_outputs" in sid for sid in removed)
    assert stray.exists()  # not deleted as a session


def test_cleanup_no_error_when_no_tool_outputs(tmp_path: Path, monkeypatch) -> None:
    import os

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    main = tmp_path / "solo.json"
    main.write_text("{}")
    os.utime(main, (0, 0))

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert "solo" in removed
