import sqlite3

from tests.integration._migration_template import apply_migrations

_LEGACY_TABLE = "_".join(("im", "channel", "allowlist"))
_LEGACY_FLAG = "_".join(("allowlist", "enforced"))


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
        connector_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(im_connectors)").fetchall()
        }
        connector_indexes = conn.execute("PRAGMA index_list(im_connectors)").fetchall()
        unique_index_names = [row[1] for row in connector_indexes if row[2] == 1]
        unique_index_columns = {
            tuple(
                info_row[2]
                for info_row in conn.execute(f"PRAGMA index_info({index_name})").fetchall()
            )
            for index_name in unique_index_names
        }

    assert _LEGACY_TABLE not in tables
    assert _LEGACY_FLAG not in connector_columns
    assert ("owner_id", "platform") in unique_index_columns
