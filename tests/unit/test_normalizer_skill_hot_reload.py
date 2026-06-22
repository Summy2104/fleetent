"""IM path triggers skill hot-reload before catalog injection (skill-external-hot-reload)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fleetent.im_gateway import normalizer


def test_maybe_refresh_calls_when_enabled() -> None:
    agent = SimpleNamespace(skill_hot_reload=True)
    with patch("fleetent.skills.registry.refresh_if_changed") as mock_refresh:
        normalizer._maybe_refresh_skills(agent)
    mock_refresh.assert_called_once()


def test_maybe_refresh_skips_when_disabled() -> None:
    agent = SimpleNamespace(skill_hot_reload=False)
    with patch("fleetent.skills.registry.refresh_if_changed") as mock_refresh:
        normalizer._maybe_refresh_skills(agent)
    mock_refresh.assert_not_called()


def test_maybe_refresh_skips_when_no_agent() -> None:
    with patch("fleetent.skills.registry.refresh_if_changed") as mock_refresh:
        normalizer._maybe_refresh_skills(None)
    mock_refresh.assert_not_called()
