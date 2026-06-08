import ast
import importlib
import pkgutil


def test_knowledge_base_package_and_layer_packages_are_importable() -> None:
    top_level = importlib.import_module("fleetent.knowledge_base")
    assert top_level.__name__ == "fleetent.knowledge_base"

    for layer in ("core", "retrieval", "ingest", "management"):
        importlib.import_module(f"fleetent.knowledge_base.{layer}")


def _package_modules(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [info.name for info in pkgutil.walk_packages(package.__path__, package.__name__ + ".")]


def _iter_imported_modules(node: ast.AST) -> list[str]:
    imported: list[str] = []
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                imported.append(alias.name)
        elif isinstance(stmt, ast.ImportFrom) and stmt.module:
            imported.append(stmt.module)
        # explicit relative imports are resolved at runtime in caller test code
    return imported


def test_knowledge_base_layer_boundary_imports_do_not_cross_hard_edges() -> None:
    for module_name in _package_modules("fleetent.knowledge_base"):
        imported_modules = set(_iter_imported_modules(_load_ast(module_name)))
        assert not _has_platform_dependency(imported_modules), (
            f"{module_name} imported platform modules"
        )
        if module_name.startswith("fleetent.knowledge_base.retrieval."):
            assert not any(
                m.startswith("fleetent.knowledge_base.ingest") for m in imported_modules
            ), f"{module_name} crossed into ingest layer"
        if module_name.startswith("fleetent.knowledge_base.core."):
            assert not any(
                m.startswith("fleetent.knowledge_base.retrieval")
                or m.startswith("fleetent.knowledge_base.ingest")
                or m.startswith("fleetent.knowledge_base.management")
                for m in imported_modules
            ), f"{module_name} depends on other non-core layers"


def _has_platform_dependency(imported_modules: set[str]) -> bool:
    return any(module.startswith("fleetent.platform") for module in imported_modules)


def _load_ast(module_name: str) -> ast.AST:
    module = importlib.import_module(module_name)
    if module.__file__ is None:
        return ast.parse("")
    with open(module.__file__, encoding="utf-8") as stream:
        return ast.parse(stream.read())
