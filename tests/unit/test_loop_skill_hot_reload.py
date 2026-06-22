"""run_stream triggers skill hot-reload before catalog injection (skill-external-hot-reload)."""

from __future__ import annotations

import inspect
from unittest.mock import patch

from fleetent.runtime import loop


def test_maybe_refresh_calls_when_enabled() -> None:
    with patch("fleetent.skills.registry.refresh_if_changed") as mock_refresh:
        loop._maybe_refresh_skills(True)
    mock_refresh.assert_called_once()


def test_maybe_refresh_skips_when_disabled() -> None:
    with patch("fleetent.skills.registry.refresh_if_changed") as mock_refresh:
        loop._maybe_refresh_skills(False)
    mock_refresh.assert_not_called()


def test_run_stream_accepts_skill_hot_reload_param_default_true() -> None:
    sig = inspect.signature(loop.run_stream)
    p = sig.parameters.get("skill_hot_reload")
    assert p is not None and p.default is True
