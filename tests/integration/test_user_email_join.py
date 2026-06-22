from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent import user_store
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    return db


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def test_users_email_partial_unique_and_normalized_on_create(db_path: Path) -> None:
    tenancy_store.create_tenant(id="tenant-a", name="Tenant A")
    tenancy_store.create_tenant(id="tenant-b", name="Tenant B")

    created, _ = user_store.create_user("Alice", email="  Alice@Co ", tenant_id="tenant-a")
    assert created.email == "alice@co"

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO users (id, name, created_at, email, tenant_id)
                VALUES (
                    'user-1',
                    'same-tenant-duplicate',
                    '2026-06-22T00:00:00+00:00',
                    'alice@co',
                    'tenant-a'
                )
                """
            )
        conn.execute(
            """
            INSERT INTO users (id, name, created_at, email, tenant_id)
            VALUES ('user-2', 'other-tenant', '2026-06-22T00:00:01+00:00', 'alice@co', 'tenant-b')
            """
        )
        conn.execute(
            """
            INSERT INTO users (id, name, created_at, email, tenant_id)
            VALUES ('user-3', 'null-1', '2026-06-22T00:00:02+00:00', NULL, 'tenant-a')
            """
        )
        conn.execute(
            """
            INSERT INTO users (id, name, created_at, email, tenant_id)
            VALUES ('user-4', 'null-2', '2026-06-22T00:00:03+00:00', NULL, 'tenant-a')
            """
        )


def test_get_by_email_is_tenant_scoped_and_normalized(db_path: Path) -> None:
    tenancy_store.create_tenant(id="tenant-a", name="Tenant A")
    tenancy_store.create_tenant(id="tenant-b", name="Tenant B")

    first, _ = user_store.create_user("Alice A", email="alice@co", tenant_id="tenant-a")
    second, _ = user_store.create_user("Alice B", email="alice@co", tenant_id="tenant-b")

    found = user_store.get_by_email("tenant-a", "  Alice@Co ")
    assert found is not None
    assert found.id == first.id

    found_other_tenant = user_store.get_by_email("tenant-b", "alice@co")
    assert found_other_tenant is not None
    assert found_other_tenant.id == second.id

    assert user_store.get_by_email("tenant-c", "alice@co") is None


def test_migration_reports_duplicate_normalized_emails_and_aborts(tmp_path: Path) -> None:
    db_path = tmp_path / "dup-users.db"
    _upgrade_to(db_path, "099")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (id, name, created_at, email, tenant_id)
            VALUES ('user-1', 'Alice 1', '2026-06-22T00:00:00+00:00', 'Alice@Co', 'default')
            """
        )
        conn.execute(
            """
            INSERT INTO users (id, name, created_at, email, tenant_id)
            VALUES ('user-2', 'Alice 2', '2026-06-22T00:00:01+00:00', ' alice@co ', 'default')
            """
        )
        conn.commit()

    with pytest.raises(RuntimeError, match="default.*alice@co"):
        _upgrade_to(db_path, "100")
