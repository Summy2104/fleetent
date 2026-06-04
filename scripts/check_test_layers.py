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
}

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
        relative_path = str(_display_path(path))
        if relative_path in active_allowlist:
            continue
        violations.extend(_scan_file(path))
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
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "fastapi.testclient":
                violations.append(_violation(path, node.lineno, "fastapi-testclient-import"))
            if module.startswith("tests.integration"):
                violations.append(_violation(path, node.lineno, "integration-test-import"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tests.integration"):
                    violations.append(_violation(path, node.lineno, "integration-test-import"))
                    break
        elif isinstance(node, ast.Call):
            if _is_test_client_call(node):
                violations.append(_violation(path, node.lineno, "fastapi-testclient-call"))
            if _is_apply_migrations_call(node):
                violations.append(_violation(path, node.lineno, "migration-helper-call"))
            if _is_alembic_upgrade_call(node):
                violations.append(_violation(path, node.lineno, "alembic-upgrade-call"))
    return violations


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
