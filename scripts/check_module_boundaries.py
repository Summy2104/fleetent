"""Check modular-monolith import boundaries."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    path: Path
    imported: str
    message: str


def find_violations(root: Path) -> list[Violation]:
    """Return imports that cross into another package's internal modules."""
    violations: list[Violation] = []
    fleetent_root = root / "fleetent"
    if not fleetent_root.exists():
        return violations

    for path in fleetent_root.rglob("*.py"):
        importer_package = _owning_package(root, path)
        if importer_package is None:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for imported in _imported_modules(tree):
            imported_package = _package_from_module(
                root=root, module=imported, importer_package=importer_package
            )
            if imported_package is None or imported_package == importer_package:
                continue
            if _is_internal_import(imported):
                violations.append(
                    Violation(
                        path=path,
                        imported=imported,
                        message=f"{path} imports internal module {imported}",
                    )
                )
    return violations


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _owning_package(root: Path, path: Path) -> str | None:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return None
    if len(parts) < 3 or parts[0] != "fleetent":
        return None
    return parts[1]


def _package_from_module(
    *, root: Path, module: str, importer_package: str
) -> str | None:
    parts = module.split(".")
    if parts[0] != "fleetent":
        return None
    if len(parts) == 2 and parts[1].startswith("_"):
        internal_dir = root / "fleetent" / importer_package / "_internal"
        if internal_dir.is_dir():
            return importer_package
        return parts[1]
    if len(parts) < 3:
        return None
    return parts[1]


def _is_internal_import(module: str) -> bool:
    parts = module.split(".")
    if len(parts) < 2:
        return False
    if parts[1].startswith("_"):
        return True
    return any(part == "_internal" or part.startswith("_") for part in parts[2:])


def main() -> int:
    root = Path("src")
    violations = find_violations(root)
    for violation in violations:
        print(violation.message)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
