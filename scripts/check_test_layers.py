from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIT_ROOT = REPO_ROOT / "tests" / "unit"

RULE_REASONS = {
    "fastapi-testclient-import": (
        "FastAPI TestClient exercises app/lifespan behavior; use tests/integration/."
    ),
    "fastapi-testclient-call": "TestClient app calls belong in tests/integration/.",
    "integration-test-import": "Unit tests must not import helpers from tests.integration.*.",
    "migration-helper-call": "Alembic-backed migration helpers belong in tests/integration/.",
    "alembic-upgrade-call": "Alembic schema lifecycle belongs in tests/integration/.",
    "sqlite-import": "SQLite-backed tests belong in tests/integration/.",
    "sqlite-connect-call": "SQLite connection tests belong in tests/integration/.",
    "production-db-path-mutation": (
        "Production DB_PATH mutation creates DB-backed tests; use tests/integration/."
    ),
    "store-init-db-call": "Production store schema initialization belongs in tests/integration/.",
    "sqlite-database-url": "SQLite DATABASE_URL runtime tests belong in tests/integration/.",
    "sqlite-create-database-call": "SQLite database runtime tests belong in tests/integration/.",
}

DB_RULES = frozenset(
    {
        "sqlite-import",
        "sqlite-connect-call",
        "production-db-path-mutation",
        "store-init-db-call",
        "sqlite-database-url",
        "sqlite-create-database-call",
    }
)

# Temporary exceptions for legacy SQLite store tests that still exercise migrated local DB
# boundaries. Keep this centralized so the owning cleanup area is visible.
LEGACY_UNIT_ALLOWLIST: dict[str, str] = {}


@dataclass(frozen=True)
class TestLayerViolation:
    path: Path
    line: int
    rule: str
    reason: str


def scan_unit_tests(
    root: Path | str = DEFAULT_UNIT_ROOT,
    *,
    allowlist: dict[str, str] | None = None,
) -> list[TestLayerViolation]:
    """Scan a unit test root for integration-only test patterns."""
    unit_root = Path(root)
    active_allowlist = LEGACY_UNIT_ALLOWLIST if allowlist is None else allowlist
    violations: list[TestLayerViolation] = []
    for path in sorted(unit_root.rglob("test_*.py")):
        file_violations = _scan_file(path)
        if _is_allowlisted(path, active_allowlist):
            file_violations = [
                violation for violation in file_violations if violation.rule in DB_RULES
            ]
        violations.extend(file_violations)
    return violations


def format_violations(violations: Iterable[TestLayerViolation]) -> str:
    return "\n".join(
        f"{violation.path}:{violation.line}: {violation.rule}: {violation.reason}"
        for violation in violations
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that tests/unit does not contain integration-layer test patterns."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(DEFAULT_UNIT_ROOT),
        help="Unit test root to scan (default: tests/unit).",
    )
    args = parser.parse_args(argv)

    violations = scan_unit_tests(Path(args.root))
    if violations:
        print(format_violations(violations))
        return 1
    return 0


def _scan_file(path: Path) -> list[TestLayerViolation]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return sorted(_scan_ast(path, tree), key=lambda violation: (violation.line, violation.rule))


def _scan_ast(path: Path, tree: ast.AST) -> list[TestLayerViolation]:
    violations: list[TestLayerViolation] = []
    db_path_mutation_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "fastapi.testclient":
                violations.append(_violation(path, node.lineno, "fastapi-testclient-import"))
            if module == "sqlite3":
                violations.append(_violation(path, node.lineno, "sqlite-import"))
            if module.startswith("tests.integration"):
                violations.append(_violation(path, node.lineno, "integration-test-import"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tests.integration"):
                    violations.append(_violation(path, node.lineno, "integration-test-import"))
                    break
                if alias.name == "sqlite3" or alias.name.startswith("sqlite3."):
                    violations.append(_violation(path, node.lineno, "sqlite-import"))
                    break
        elif isinstance(node, ast.Call):
            if _is_test_client_call(node):
                violations.append(_violation(path, node.lineno, "fastapi-testclient-call"))
            if _is_apply_migrations_call(node):
                violations.append(_violation(path, node.lineno, "migration-helper-call"))
            if _is_alembic_upgrade_call(node):
                violations.append(_violation(path, node.lineno, "alembic-upgrade-call"))
            if _is_sqlite_connect_call(node):
                violations.append(_violation(path, node.lineno, "sqlite-connect-call"))
            if _is_db_path_monkeypatch_call(node):
                db_path_mutation_lines.append(node.lineno)
            if _is_store_init_db_call(node):
                violations.append(_violation(path, node.lineno, "store-init-db-call"))
            if _is_sqlite_database_url_call(node):
                violations.append(_violation(path, node.lineno, "sqlite-database-url"))
            if _is_sqlite_create_database_call(node):
                violations.append(_violation(path, node.lineno, "sqlite-create-database-call"))
        elif isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            if _mutates_db_path(node):
                db_path_mutation_lines.append(node.lineno)
            if _assigns_sqlite_database_url(node):
                violations.append(_violation(path, node.lineno, "sqlite-database-url"))
    for line in _db_backed_path_mutation_lines(tree, db_path_mutation_lines):
        violations.append(_violation(path, line, "production-db-path-mutation"))
    return violations


def _is_allowlisted(path: Path, allowlist: dict[str, str]) -> bool:
    display_path = str(_display_path(path))
    return display_path in allowlist or path.name in allowlist


def _db_backed_path_mutation_lines(tree: ast.AST, mutation_lines: list[int]) -> list[int]:
    if not mutation_lines:
        return []
    db_backed_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        function_mutations = [
            line
            for line in mutation_lines
            if node.lineno <= line <= (node.end_lineno or node.lineno)
        ]
        if not function_mutations:
            continue
        if not node.name.startswith("test_") or _function_exercises_db_behavior(node):
            db_backed_lines.update(function_mutations)
    return sorted(db_backed_lines)


def _function_exercises_db_behavior(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if (
            _is_sqlite_connect_call(child)
            or _is_store_init_db_call(child)
            or _is_sqlite_database_url_call(child)
            or _is_sqlite_create_database_call(child)
            or _is_likely_store_runtime_call(child)
        ):
            return True
    return False


def _is_likely_store_runtime_call(node: ast.Call) -> bool:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id.startswith(
            (
                "add_",
                "block_",
                "check_",
                "get_",
                "list_",
                "load_",
                "query_",
                "record_",
                "remove_",
                "resolve_",
                "save_",
                "set_",
                "upsert",
            )
        )
    if isinstance(function, ast.Attribute):
        if isinstance(function.value, ast.Name) and function.value.id == "monkeypatch":
            return False
        return function.attr not in {"read_text", "write_text", "exists", "glob", "mkdir"}
    return False


def _is_test_client_call(node: ast.Call) -> bool:
    function = node.func
    return isinstance(function, ast.Name) and function.id == "TestClient"


def _is_apply_migrations_call(node: ast.Call) -> bool:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id == "apply_migrations"
    if isinstance(function, ast.Attribute):
        return function.attr == "apply_migrations"
    return False


def _is_alembic_upgrade_call(node: ast.Call) -> bool:
    function = node.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "upgrade"
        and isinstance(function.value, ast.Name)
        and function.value.id == "command"
    )


def _is_sqlite_connect_call(node: ast.Call) -> bool:
    function = node.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "connect"
        and isinstance(function.value, ast.Name)
        and function.value.id == "sqlite3"
    )


def _is_db_path_monkeypatch_call(node: ast.Call) -> bool:
    function = node.func
    if not (
        isinstance(function, ast.Attribute)
        and function.attr == "setattr"
        and isinstance(function.value, ast.Name)
        and function.value.id == "monkeypatch"
    ):
        return False
    if len(node.args) >= 2 and _string_value(node.args[1]) == "DB_PATH":
        return True
    return bool(node.args and (_string_value(node.args[0]) or "").endswith(".DB_PATH"))


def _is_store_init_db_call(node: ast.Call) -> bool:
    function = node.func
    if isinstance(function, ast.Attribute):
        return function.attr == "_init_db"
    return isinstance(function, ast.Name) and function.id == "_init_db"


def _is_sqlite_database_url_call(node: ast.Call) -> bool:
    function = node.func
    if not isinstance(function, ast.Attribute):
        return False
    if function.attr == "setenv" and len(node.args) >= 2:
        return _string_value(node.args[0]) == "DATABASE_URL" and _is_sqlite_url(node.args[1])
    return False


def _is_sqlite_create_database_call(node: ast.Call) -> bool:
    function = node.func
    if isinstance(function, ast.Name):
        is_create_database = function.id == "create_database"
    elif isinstance(function, ast.Attribute):
        is_create_database = function.attr == "create_database"
    else:
        is_create_database = False
    return is_create_database and any(_is_sqlite_url(arg) for arg in node.args)


def _mutates_db_path(node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> bool:
    targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        if isinstance(target, ast.Attribute) and target.attr == "DB_PATH":
            return True
        if isinstance(target, ast.Name) and target.id == "DB_PATH":
            return True
    return False


def _assigns_sqlite_database_url(node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> bool:
    value = getattr(node, "value", None)
    if value is None or not _is_sqlite_url(value):
        return False
    targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        if isinstance(target, ast.Subscript) and _string_value(target.slice) == "DATABASE_URL":
            return True
        if isinstance(target, ast.Name) and target.id == "DATABASE_URL":
            return True
    return False


def _is_sqlite_url(node: ast.AST) -> bool:
    value = _string_value(node)
    return value is not None and value.startswith("sqlite:///")


def _string_value(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _violation(path: Path, line: int, rule: str) -> TestLayerViolation:
    return TestLayerViolation(
        path=_display_path(path), line=line, rule=rule, reason=RULE_REASONS[rule]
    )


def _display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


if __name__ == "__main__":
    raise SystemExit(main())
