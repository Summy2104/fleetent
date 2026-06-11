"""DATABASE_URL resolution in observability.traces consolidates the bypass."""

from pathlib import Path

import pytest

from fleetent.observability import traces


def test_database_url_env_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom/place.db")
    assert traces._database_url() == "sqlite:///custom/place.db"


def test_default_database_url_derives_from_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    assert traces._database_url() == f"sqlite:///{tmp_path / 'data' / 'management.db'}"


def test_no_hardcoded_relative_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    assert traces._database_url() != "sqlite:///data/fleetent.db"
