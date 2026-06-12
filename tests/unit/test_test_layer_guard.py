from __future__ import annotations

from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_guard_reports_unit_layer_violations_with_file_line_and_reason(tmp_path):
    from scripts.check_test_layers import scan_unit_tests

    unit_root = tmp_path / "tests" / "unit"
    _write(
        unit_root / "test_bad_fastapi.py",
        "\n".join(
            [
                "from fastapi.testclient import TestClient",
                "",
                "def test_lifespan(app):",
                "    with TestClient(app) as client:",
                "        assert client.get('/health').status_code == 200",
            ]
        ),
    )
    _write(
        unit_root / "test_bad_migrations.py",
        "\n".join(
            [
                "from alembic import command",
                "from tests.integration.test_migrations import apply_migrations",
                "",
                "def test_schema(db_path, cfg):",
                "    apply_migrations(db_path)",
                "    command.upgrade(cfg, 'head')",
            ]
        ),
    )

    violations = scan_unit_tests(unit_root)

    diagnostics = {
        (violation.path.name, violation.line, violation.rule) for violation in violations
    }
    assert diagnostics == {
        ("test_bad_fastapi.py", 1, "fastapi-testclient-import"),
        ("test_bad_fastapi.py", 4, "fastapi-testclient-call"),
        ("test_bad_migrations.py", 2, "integration-test-import"),
        ("test_bad_migrations.py", 5, "migration-helper-call"),
        ("test_bad_migrations.py", 6, "alembic-upgrade-call"),
    }
    assert all(violation.reason for violation in violations)


def test_guard_allows_pure_unit_fixtures(tmp_path):
    from scripts.check_test_layers import scan_unit_tests

    unit_root = tmp_path / "tests" / "unit"
    _write(
        unit_root / "test_config_parser.py",
        "\n".join(
            [
                "def test_parser_uses_tmp_path_for_injected_file_boundary(tmp_path):",
                "    config = tmp_path / 'config.yaml'",
                "    config.write_text('enabled: true', encoding='utf-8')",
                "    assert config.read_text(encoding='utf-8') == 'enabled: true'",
            ]
        ),
    )

    assert scan_unit_tests(unit_root) == []


def test_guard_reports_real_database_unit_dependencies(tmp_path):
    from scripts.check_test_layers import scan_unit_tests

    unit_root = tmp_path / "tests" / "unit"
    _write(
        unit_root / "test_bad_db_patterns.py",
        "\n".join(
            [
                "import sqlite3",
                "from fleetent import user_store",
                "from fleetent.infrastructure.database import create_database",
                "",
                "def test_store_uses_tmp_sqlite(tmp_path, monkeypatch):",
                "    monkeypatch.setattr(user_store, 'DB_PATH', tmp_path / 'users.db')",
                "    user_store._init_db()",
                "    with sqlite3.connect(tmp_path / 'users.db') as conn:",
                "        assert conn.execute('select 1').fetchone()[0] == 1",
                "",
                "def test_runtime_sqlite_url(monkeypatch):",
                "    monkeypatch.setenv('DATABASE_URL', 'sqlite:///tmp/fleetent.db')",
                "    create_database('sqlite:///tmp/fleetent.db')",
            ]
        ),
    )

    violations = scan_unit_tests(unit_root)

    diagnostics = {(violation.line, violation.rule) for violation in violations}
    assert diagnostics == {
        (1, "sqlite-import"),
        (6, "production-db-path-mutation"),
        (7, "store-init-db-call"),
        (8, "sqlite-connect-call"),
        (12, "sqlite-database-url"),
        (13, "sqlite-create-database-call"),
    }
    assert all(violation.reason for violation in violations)


def test_guard_allows_read_only_db_symbol_compatibility_assertions(tmp_path):
    from scripts.check_test_layers import scan_unit_tests

    unit_root = tmp_path / "tests" / "unit"
    _write(
        unit_root / "test_compat.py",
        "\n".join(
            [
                "def test_im_module_does_not_reexport_identity_db_path():",
                "    from fleetent.platform import im_gateway_management as im",
                "    assert not hasattr(im, 'DB_PATH')",
                "",
                "def test_identity_submodule_drops_db_path_reexport():",
                "    from fleetent.platform.im_gateway_management import identity",
                "    assert not hasattr(identity, 'DB_PATH')",
                "",
                "def test_legacy_shim_reexports_same_object():",
                "    from fleetent.platform.im_gateway_management import connector_store",
                "    from fleetent.platform.im_gateway_management import im_connector_store",
                "    assert im_connector_store.get_connector is connector_store.get_connector",
            ]
        ),
    )

    assert scan_unit_tests(unit_root) == []


def test_guard_does_not_allowlist_real_database_dependencies(tmp_path):
    from scripts.check_test_layers import scan_unit_tests

    unit_root = tmp_path / "tests" / "unit"
    _write(
        unit_root / "test_allowlisted_db.py",
        "\n".join(
            [
                "import sqlite3",
                "",
                "def test_db(tmp_path):",
                "    sqlite3.connect(tmp_path / 'x.db')",
            ]
        ),
    )

    violations = scan_unit_tests(
        unit_root,
        allowlist={"test_allowlisted_db.py": "documented non-DB false positive"},
    )

    assert {(violation.line, violation.rule) for violation in violations} == {
        (1, "sqlite-import"),
        (4, "sqlite-connect-call"),
    }


def test_guard_reports_db_path_with_unqualified_persistence_helpers(tmp_path):
    from scripts.check_test_layers import scan_unit_tests

    unit_root = tmp_path / "tests" / "unit"
    _write(
        unit_root / "test_bad_unqualified_store.py",
        "\n".join(
            [
                "from fleetent.runtime.context import load_anti_flap_state, save_anti_flap_state",
                "import fleetent.runtime.context as cm",
                "",
                "def test_roundtrip(tmp_path, monkeypatch):",
                "    monkeypatch.setattr(cm, 'DB_PATH', tmp_path / 'users.db')",
                "    save_anti_flap_state('s1', object())",
                "    assert load_anti_flap_state('s1') is not None",
            ]
        ),
    )

    violations = scan_unit_tests(unit_root)

    assert {(violation.line, violation.rule) for violation in violations} == {
        (5, "production-db-path-mutation")
    }
