"""Central runtime path resolver.

All config/data paths derive from here. Resolution precedence for the base
directory:

1. ``FLEETENT_HOME`` environment variable, when set (explicit override).
2. The fleetent repository root, when running from inside a checkout
   (development): zero-config so ``uv run`` keeps using ``./config`` + ``./data``.
3. ``~/.fleetent`` fallback, for globally-installed, working-directory-decoupled
   use.

This module is the single place that reads ``FLEETENT_HOME``; business modules
import the accessors below rather than re-deriving paths.
"""

import os
from pathlib import Path

# How many parent levels to scan for a repo marker when detecting a checkout.
_REPO_SCAN_DEPTH = 3
_DEFAULT_HOME_DIRNAME = ".fleetent"
_REPO_NAME_MARKER = 'name = "fleetent"'


def _has_repo_marker(directory: Path) -> bool:
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        try:
            if _REPO_NAME_MARKER in pyproject.read_text():
                return True
        except OSError:
            pass
    return (directory / "config").is_dir()


def _repo_root() -> Path | None:
    cwd = Path.cwd()
    for candidate in (cwd, *list(cwd.parents)[:_REPO_SCAN_DEPTH]):
        if _has_repo_marker(candidate):
            return candidate
    return None


def base_dir() -> Path:
    """Resolve the base directory holding ``config/`` and ``data/``."""
    explicit = os.environ.get("FLEETENT_HOME")
    if explicit:
        return Path(explicit).expanduser()
    repo = _repo_root()
    if repo is not None:
        return repo
    return Path.home() / _DEFAULT_HOME_DIRNAME


def config_dir() -> Path:
    return base_dir() / "config"


def data_dir() -> Path:
    return base_dir() / "data"


def settings_yaml_path() -> Path:
    return config_dir() / "settings.yaml"


def sessions_dir() -> Path:
    return data_dir() / "sessions"
