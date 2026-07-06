"""Integration test: migration 117 — skills_subdir + auto_open_pr default flip.

Verifies upgrading to head adds the nullable skills_subdir TEXT column to track
which subdirectory of an external git repo contains the skill definitions (NULL
means repo root, preserving existing behavior). Also flips auto_open_pr default
from 1 to 0 and converts all existing rows from auto_open_pr=1 to 0 (feature
never shipped, safe to rewrite history). Tests idempotency and downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _run_migrations(db_path, target: str = "head") -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    # Use downgrade for non-head targets, upgrade for head
    if target == "head":
        command.upgrade(cfg, target)
    else:
        command.downgrade(cfg, target)


def test_skills_subdir_column_added(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        inspector = sa.inspect(engine)
        assert inspector.has_table("skill_git_source")
        cols = {c["name"] for c in inspector.get_columns("skill_git_source")}
        assert "skills_subdir" in cols
    finally:
        engine.dispose()


def test_skills_subdir_nullable_and_readable(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO skill_git_source (id) VALUES ('default')"))
            row = conn.execute(
                sa.text("SELECT id, skills_subdir FROM skill_git_source WHERE id = 'default'")
            ).fetchone()
        assert row is not None
        assert row[0] == "default"
        assert row[1] is None  # skills_subdir defaults NULL
    finally:
        engine.dispose()


def test_skills_subdir_writable(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO skill_git_source (id) VALUES ('default')"))
            conn.execute(
                sa.text("UPDATE skill_git_source SET skills_subdir = :subdir WHERE id = 'default'"),
                {"subdir": "skills/"},
            )
            row = conn.execute(
                sa.text("SELECT skills_subdir FROM skill_git_source WHERE id = 'default'")
            ).fetchone()
        assert row is not None
        assert row[0] == "skills/"
    finally:
        engine.dispose()


def test_auto_open_pr_default_flipped_to_zero(tmp_path, monkeypatch) -> None:
    """After migration 117, new INSERTs without explicit auto_open_pr default to 0."""
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO skill_git_source (id) VALUES ('default')"))
            row = conn.execute(
                sa.text("SELECT auto_open_pr FROM skill_git_source WHERE id = 'default'")
            ).fetchone()
        assert row is not None
        assert row[0] == 0  # auto_open_pr now defaults to 0
    finally:
        engine.dispose()


def test_existing_auto_open_pr_1_converged_to_0(tmp_path, monkeypatch) -> None:
    """Existing rows with auto_open_pr=1 are converged to 0 during migration."""
    from alembic import command

    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")

    # Upgrade to 116 (just before our migration)
    command.upgrade(cfg, "116")

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            # Insert a row with auto_open_pr=1 (migration 115 default)
            conn.execute(
                sa.text("INSERT INTO skill_git_source (id, auto_open_pr) VALUES ('default', 1)")
            )
            check1 = conn.execute(
                sa.text("SELECT auto_open_pr FROM skill_git_source WHERE id = 'default'")
            ).fetchone()
        assert check1 is not None
        assert check1[0] == 1
    finally:
        engine.dispose()

    # Now upgrade to 117 (head)
    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            check2 = conn.execute(
                sa.text("SELECT auto_open_pr FROM skill_git_source WHERE id = 'default'")
            ).fetchone()
        assert check2 is not None
        assert check2[0] == 0  # converged to 0
    finally:
        engine.dispose()


def test_idempotent_upgrade(tmp_path, monkeypatch) -> None:
    """Running migration 117 twice is safe (idempotent)."""
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO skill_git_source (id) VALUES ('default')"))
            conn.execute(
                sa.text("UPDATE skill_git_source SET skills_subdir = :subdir WHERE id = 'default'"),
                {"subdir": "skills/"},
            )
            before = conn.execute(
                sa.text("SELECT id, skills_subdir FROM skill_git_source WHERE id = 'default'")
            ).fetchone()
        assert before is not None
        assert before[1] == "skills/"
    finally:
        engine.dispose()

    # Run migration to head again (should be idempotent)
    _run_migrations(db, "head")

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            after = conn.execute(
                sa.text("SELECT id, skills_subdir FROM skill_git_source WHERE id = 'default'")
            ).fetchone()
        assert after is not None
        assert after[1] == "skills/"  # unchanged
    finally:
        engine.dispose()


def test_downgrade_removes_skills_subdir(tmp_path, monkeypatch) -> None:
    """Downgrading from 117 to 116 removes the skills_subdir column."""
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db, "head")

    # Verify column exists at head
    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        inspector = sa.inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("skill_git_source")}
        assert "skills_subdir" in cols
    finally:
        engine.dispose()

    # Downgrade to 116
    _run_migrations(db, "116")

    # Verify column is gone
    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        inspector = sa.inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("skill_git_source")}
        assert "skills_subdir" not in cols
    finally:
        engine.dispose()
