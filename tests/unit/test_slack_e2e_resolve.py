"""Unit: helper resolve 的前置校验结果结构（缺失即 blocked、命名缺失项）。"""

from __future__ import annotations

from tests.e2e.slack_autonomous._pure import build_resolve_report


def test_all_preconditions_ok_is_ready() -> None:
    r = build_resolve_report(
        token_ok=True,
        bot_user_id="UBOT",
        bot_found=True,
        channel_ok=True,
        missing_scopes=(),
    )
    assert r["ok"] is True
    assert r["status"] == "ready"


def test_missing_token_is_blocked_and_named() -> None:
    r = build_resolve_report(
        token_ok=False,
        bot_user_id=None,
        bot_found=False,
        channel_ok=False,
        missing_scopes=(),
    )
    assert r["ok"] is False
    assert r["status"] == "blocked"
    assert "token" in r["missing"]


def test_missing_bot_and_channel_named() -> None:
    r = build_resolve_report(
        token_ok=True,
        bot_user_id="UBOT",
        bot_found=False,
        channel_ok=False,
        missing_scopes=(),
    )
    assert r["ok"] is False
    assert any("bot" in m for m in r["missing"])
    assert any("channel" in m for m in r["missing"])


def test_missing_scope_listed() -> None:
    r = build_resolve_report(
        token_ok=True,
        bot_user_id="UBOT",
        bot_found=True,
        channel_ok=True,
        missing_scopes=("files:write",),
    )
    assert r["ok"] is False
    assert any("files:write" in m for m in r["missing"])
