"""Unit tests: per-agent user.md instruction file + /user command handler.

Pure file I/O under the pinned FLEETENT_HOME (paths.agent_home_dir evaluated at
call time), mirroring test_session_todo_store.py. No SQLite, no platform.
"""

from __future__ import annotations

from pathlib import Path

from fleetent import paths
from fleetent.runtime import user_instructions as ui


def _user_md(agent_id: str) -> Path:
    return paths.agent_home_dir(agent_id) / ui.USER_MD_FILENAME


# --- load -------------------------------------------------------------------


def test_load_missing_returns_empty() -> None:
    assert ui.load("default") == ""


def test_load_reads_content() -> None:
    p = _user_md("default")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("永远用中文回答", encoding="utf-8")
    assert ui.load("default") == "永远用中文回答"


def test_load_truncates_over_limit_disk_unchanged() -> None:
    p = _user_md("default")
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = "x" * (ui._MAX_CHARS + 500)
    p.write_text(raw, encoding="utf-8")

    loaded = ui.load("default")

    # Content portion capped at the limit; truncation is visible.
    assert len(loaded) <= ui._MAX_CHARS + len(ui._TRUNCATION_MARKER)
    assert loaded.startswith("x" * ui._MAX_CHARS)
    assert ui._TRUNCATION_MARKER in loaded
    # Disk original is left intact.
    assert p.read_text(encoding="utf-8") == raw


# --- handle_user_command: parsing -------------------------------------------


def test_handle_non_command_returns_none() -> None:
    assert ui.handle_user_command("default", "你好") is None
    assert ui.handle_user_command("default", "  hi  ") is None


def test_handle_lookalike_not_matched() -> None:
    # "/users" must not be treated as the /user command.
    assert ui.handle_user_command("default", "/users") is None
    assert ui.handle_user_command("default", "/userfoo bar") is None


def test_handle_bare_user_empty_hint() -> None:
    reply = ui.handle_user_command("default", "/user")
    assert reply is not None
    assert "尚未设置" in reply


def test_handle_bare_user_shows_content() -> None:
    p = _user_md("default")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("永远用中文回答", encoding="utf-8")
    reply = ui.handle_user_command("default", "/user")
    assert reply is not None
    assert "永远用中文回答" in reply


# --- handle_user_command: append --------------------------------------------


def test_append_to_empty_creates_file() -> None:
    reply = ui.handle_user_command("default", "/user 永远用中文回答")
    assert reply is not None
    assert ui.load("default") == "永远用中文回答"
    assert _user_md("default").exists()


def test_append_to_existing_keeps_prior_lines() -> None:
    ui.handle_user_command("default", "/user 永远用中文回答")
    ui.handle_user_command("default", "/user 回答要简短")
    loaded = ui.load("default")
    assert "永远用中文回答" in loaded
    assert "回答要简短" in loaded
    # Two distinct lines.
    assert loaded.count("\n") >= 1


def test_append_atomic_no_tmp_leftover() -> None:
    ui.handle_user_command("default", "/user 永远用中文回答")
    agent_dir = paths.agent_home_dir("default")
    assert list(agent_dir.glob("*.tmp")) == []


# --- handle_user_command: clear ---------------------------------------------


def test_clear_empties_file() -> None:
    ui.handle_user_command("default", "/user 永远用中文回答")
    reply = ui.handle_user_command("default", "/user clear")
    assert reply is not None
    assert ui.load("default") == ""


def test_clear_idempotent_when_absent() -> None:
    reply = ui.handle_user_command("default", "/user clear")  # no file yet
    assert reply is not None  # no raise
    assert ui.load("default") == ""
