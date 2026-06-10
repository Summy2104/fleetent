"""Unit tests for TUI token-based authentication in standalone agent.

Tests the _validate_tui_token() helper that guards the /ws endpoint,
avoiding TestClient (not allowed in unit layer per CLAUDE.md).
"""

from __future__ import annotations

import pytest


def test_validate_tui_token_accepts_matching_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-test-token-12345")
    from fleetent.identity import Principal
    from fleetent.runtime.agent_app import _validate_tui_token

    result = _validate_tui_token("Bearer ma-test-token-12345")
    assert isinstance(result, Principal)
    assert result.user_id == "local"


def test_validate_tui_token_rejects_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-correct-token")
    from fleetent.runtime.agent_app import _validate_tui_token

    assert _validate_tui_token("Bearer ma-wrong-token") is None


def test_validate_tui_token_rejects_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FLEETENT_TUI_TOKEN", raising=False)
    from fleetent.runtime.agent_app import _validate_tui_token

    assert _validate_tui_token("Bearer ma-anything") is None


def test_validate_tui_token_rejects_missing_bearer_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-token")
    from fleetent.runtime.agent_app import _validate_tui_token

    assert _validate_tui_token("ma-token") is None
