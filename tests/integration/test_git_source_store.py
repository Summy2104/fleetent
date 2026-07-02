"""Integration test: git_source_store — single-row external git source config + sync state.

Real SQLite + Alembic (table created by migration 113). Exercises get_config /
set_config (upsert, idempotent, unknown-field rejection) and record_sync (updates only
the sync-state columns, leaves config untouched).
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.skill_management import git_source_store


def _migrated_db(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def test_get_config_none_when_unset(tmp_path, monkeypatch) -> None:
    _migrated_db(tmp_path, monkeypatch)
    assert git_source_store.get_config() is None


def test_set_config_upsert_idempotent(tmp_path, monkeypatch) -> None:
    _migrated_db(tmp_path, monkeypatch)

    git_source_store.set_config(enabled=1, remote_url="https://git.example/x.git", branch="main")
    cfg = git_source_store.get_config()
    assert cfg is not None
    assert cfg["id"] == "default"
    assert cfg["enabled"] == 1
    assert cfg["remote_url"] == "https://git.example/x.git"
    assert cfg["branch"] == "main"

    # second upsert updates only given fields, single row preserved
    git_source_store.set_config(branch="develop")
    cfg2 = git_source_store.get_config()
    assert cfg2["branch"] == "develop"
    assert cfg2["remote_url"] == "https://git.example/x.git"  # untouched


def test_record_sync_updates_only_state(tmp_path, monkeypatch) -> None:
    _migrated_db(tmp_path, monkeypatch)
    git_source_store.set_config(enabled=1, remote_url="https://git.example/x.git")

    git_source_store.record_sync(commit="abc123", at="2026-06-30T00:00:00+00:00", error=None)
    cfg = git_source_store.get_config()
    assert cfg["last_synced_commit"] == "abc123"
    assert cfg["last_sync_at"] == "2026-06-30T00:00:00+00:00"
    assert cfg["last_sync_error"] is None
    assert cfg["remote_url"] == "https://git.example/x.git"  # config untouched

    git_source_store.record_sync(commit="abc123", at="2026-06-30T00:01:00+00:00", error="boom")
    cfg2 = git_source_store.get_config()
    assert cfg2["last_sync_error"] == "boom"


def test_set_config_rejects_unknown_field(tmp_path, monkeypatch) -> None:
    _migrated_db(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        git_source_store.set_config(bogus="x")


def test_set_config_skills_subdir(tmp_path, monkeypatch) -> None:
    _migrated_db(tmp_path, monkeypatch)

    git_source_store.set_config(
        enabled=1, remote_url="https://git.example/x.git", skills_subdir="skills"
    )
    cfg = git_source_store.get_config()
    assert cfg is not None
    assert cfg["skills_subdir"] == "skills"

    # upsert without skills_subdir leaves it untouched
    git_source_store.set_config(branch="develop")
    cfg2 = git_source_store.get_config()
    assert cfg2["skills_subdir"] == "skills"
    assert cfg2["branch"] == "develop"


def test_set_config_skills_subdir_unset_is_none(tmp_path, monkeypatch) -> None:
    _migrated_db(tmp_path, monkeypatch)

    git_source_store.set_config(enabled=1, remote_url="https://git.example/x.git")
    cfg = git_source_store.get_config()
    assert cfg is not None
    assert cfg["skills_subdir"] is None
