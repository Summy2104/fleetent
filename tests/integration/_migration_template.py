"""Shared, process-cached Alembic migration helper for integration tests.

Running ``upgrade head`` over every migration once per DB-backed test dominated the
integration suite's wall time. SQLite is a single file and a fully-migrated database
(including the ``alembic_version`` row) is reproducible by byte copy, so we migrate once
into a template and copy it for every caller. Each test still gets its own file, so
per-test isolation is unchanged.
"""

from __future__ import annotations

import atexit
import functools
import shutil
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

# Absolute so callers that chdir (e.g. server tests) still resolve the scripts.
_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


@functools.lru_cache(maxsize=1)
def _template_db() -> Path:
    """Build the migrated template once per process and return its path.

    migrations/env.py prefers DATABASE_URL over the ini url; whichever test
    happens to trigger the lazy build may have it monkeypatched, which would
    migrate that test's database instead of the template (head.db then never
    exists and every later copy fails). Scrub it for the build.
    """
    import os

    tmp_dir = Path(tempfile.mkdtemp(prefix="fleetent_migr_tpl_"))
    atexit.register(shutil.rmtree, tmp_dir, ignore_errors=True)
    template = tmp_dir / "head.db"
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{template}")
    saved = os.environ.pop("DATABASE_URL", None)
    try:
        command.upgrade(cfg, "head")
    finally:
        if saved is not None:
            os.environ["DATABASE_URL"] = saved
    return template


def apply_migrations(db_path: Path) -> None:
    """Materialize a fully-migrated SQLite database at ``db_path`` by copying the template."""
    shutil.copy(_template_db(), db_path)
