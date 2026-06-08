"""Residual fallback defaults also derive from the resolver (no CWD-relative leak)."""

from pathlib import Path

import pytest

from fleetent import structured_logging


def test_logging_config_default_directory_follows_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    assert structured_logging._LoggingConfig().directory == tmp_path / "data" / "logs"


def test_diagnostics_default_data_dir_follows_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fleetent import paths
    from fleetent.observability import diagnostics

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    # The module no longer hardcodes a CWD-relative "data" fallback.
    assert diagnostics._default_data_dir() == paths.data_dir()
