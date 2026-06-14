import sqlite3

from tests.integration._migration_template import apply_migrations

_LEGACY_TABLE = "_".join(("im", "channel", "allowlist"))
_LEGACY_FLAG = "_".join(("allowlist", "enforced"))
_OWNER_TABLE = "_".join(("im", "connectors"))


def test_head_descope_legacy_im_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert _LEGACY_TABLE not in tables
    assert _OWNER_TABLE not in tables
