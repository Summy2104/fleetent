import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INTELLIGENCE_ROOT = REPO_ROOT / "src" / "fleetent" / "intelligence"
GOVERNANCE_ROOT = REPO_ROOT / "src" / "fleetent" / "governance"


def _read_source(relative_path: str) -> str:
    module_path = REPO_ROOT / "src" / "fleetent" / relative_path
    return module_path.read_text(encoding="utf-8")


def test_reflection_module_isolated_from_platform_and_ingest() -> None:
    module_path = REPO_ROOT / "src" / "fleetent" / "intelligence" / "reflection.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module == "fleetent.intelligence" and any(
                alias.name == "knowledge_base" for alias in node.names
            ):
                raise AssertionError("reflection imports knowledge_base at module scope")
            if node.module and re.search(r"\bfleetent\.platform\b", node.module):
                raise AssertionError("reflection imports platform at module scope")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "fleetent.platform" not in alias.name


def test_governance_modules_are_isolated_from_platform() -> None:
    for module_path in GOVERNANCE_ROOT.glob("*.py"):
        if module_path.name == "__init__.py":
            continue
        source = module_path.read_text(encoding="utf-8")
        assert "fleetent.platform" not in source


def test_memory_modules_do_not_import_reflection() -> None:
    for module_path in INTELLIGENCE_ROOT.glob("memory/*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and (
                (
                    node.module == "fleetent.intelligence"
                    and any(alias.name == "reflection" for alias in node.names)
                )
                or (node.module and node.module.startswith("fleetent.intelligence.reflection"))
            ):
                raise AssertionError(f"{module_path} imports reflection at module scope")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "fleetent.intelligence.reflection" or alias.name.startswith(
                        "fleetent.intelligence.reflection."
                    ):
                        raise AssertionError(f"{module_path} imports reflection at module scope")
