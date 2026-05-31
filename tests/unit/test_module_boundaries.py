from pathlib import Path

from scripts.check_module_boundaries import find_violations


def test_reports_cross_package_internal_import(tmp_path: Path) -> None:
    root = tmp_path / "src"
    importer = root / "fleetent" / "runtime" / "agent.py"
    imported = root / "fleetent" / "intelligence" / "_internal" / "store.py"
    importer.parent.mkdir(parents=True)
    imported.parent.mkdir(parents=True)
    importer.write_text("from fleetent.intelligence._internal import store\n")
    imported.write_text("VALUE = 1\n")

    violations = find_violations(root)

    assert len(violations) == 1
    assert violations[0].path == importer
    assert violations[0].imported == "fleetent.intelligence._internal"


def test_allows_same_package_internal_import(tmp_path: Path) -> None:
    root = tmp_path / "src"
    importer = root / "fleetent" / "intelligence" / "memory.py"
    imported = root / "fleetent" / "intelligence" / "_internal" / "store.py"
    importer.parent.mkdir(parents=True)
    imported.parent.mkdir(parents=True)
    importer.write_text("from fleetent.intelligence._internal import store\n")
    imported.write_text("VALUE = 1\n")

    assert find_violations(root) == []


def test_reports_cross_package_leading_underscore_import(tmp_path: Path) -> None:
    root = tmp_path / "src"
    importer = root / "fleetent" / "platform" / "users.py"
    imported = root / "fleetent" / "observability" / "_writer.py"
    importer.parent.mkdir(parents=True)
    imported.parent.mkdir(parents=True)
    importer.write_text("import fleetent.observability._writer\n")
    imported.write_text("VALUE = 1\n")

    violations = find_violations(root)

    assert len(violations) == 1
    assert violations[0].imported == "fleetent.observability._writer"
