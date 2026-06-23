"""Config/server path constants derive from the central resolver."""

from pathlib import Path

import pytest

from fleetent.config import Settings


def _assert_derivation_in_clean_env(code: str) -> None:
    """Run an import-time derivation assertion in a child interpreter.

    Constants are frozen at import. Comparing an in-process constant against a
    call-time paths.X() is fragile: an ambient FLEETENT_HOME in the developer
    shell freezes a different base than a post-delenv call resolves. A child
    interpreter with FLEETENT_HOME stripped checks constant == derivation under
    one consistent environment.
    """
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "FLEETENT_HOME"}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_config_module_constants_derive_from_paths() -> None:
    _assert_derivation_in_clean_env(
        "from fleetent import paths; import fleetent.config as cfg; "
        "assert cfg.PLATFORM_YAML_PATH == paths.platform_yaml_path(), cfg.PLATFORM_YAML_PATH"
    )


def test_settings_default_paths_follow_fleetent_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.setattr("fleetent.config.PLATFORM_YAML_PATH", tmp_path / "missing.yaml")

    s = Settings()

    assert s.database_url == f"sqlite:///{tmp_path / 'management.db'}"
    # Blank means "resolve at runtime": configure_structured_logging falls back to
    # data_dir()/logs when directory is empty, so the effective log path still follows
    # FLEETENT_HOME — only the stored default changed from absolute to blank.
    assert s.observability.logging.directory == ""
