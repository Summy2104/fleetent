"""Guards that the test suite never resolves paths into the real ~/.fleetent.

Regression: configurable-data-home added a `~/.fleetent` home fallback. A test
that runs outside a repo checkout without FLEETENT_HOME set would resolve
config/data (and logging) into the real user home, leaking pytest artifacts
there. An autouse fixture in conftest must pin FLEETENT_HOME to a temp dir.
"""

import os
from pathlib import Path

from fleetent import paths


def test_fleetent_home_is_pinned_to_temp() -> None:
    fh = os.environ.get("FLEETENT_HOME")
    assert fh, "FLEETENT_HOME must be set by an autouse isolation fixture"
    base = paths.base_dir()
    assert base == Path(fh)
    # Never the real user home.
    assert base != Path.home() / ".fleetent"


def test_logging_default_dir_never_leaks_to_real_home(monkeypatch, tmp_path) -> None:
    # Reproduce the leak path: chdir outside any repo, configure logging with no
    # explicit directory. It must resolve under the isolated FLEETENT_HOME.
    monkeypatch.chdir(tmp_path)
    from fleetent.observability import structured_logging

    structured_logging.configure_structured_logging()
    log_dir = structured_logging._config.directory

    real_home_fleetent = Path.home() / ".fleetent"
    assert real_home_fleetent != log_dir
    assert real_home_fleetent not in log_dir.parents
