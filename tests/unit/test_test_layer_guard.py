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
