"""Load workflow definitions from the workflows directory.

A workflow is identified by its file stem: ``<name>.yaml`` in ``paths.workflows_dir()``.
Loading parses YAML then runs full definition validation. A missing/empty
directory is a normal "no workflows" state, not an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from fleetent import paths
from fleetent.workflow.definition import WorkflowDef, parse_definition
from fleetent.workflow.errors import WorkflowDefinitionError, WorkflowNotFoundError

_SUFFIXES = (".yaml", ".yml")


def _dir() -> Path:
    return paths.workflows_dir()


def _path_for(name: str) -> Path | None:
    base = _dir()
    for suffix in _SUFFIXES:
        candidate = base / f"{name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _available_names() -> list[str]:
    base = _dir()
    if not base.is_dir():
        return []
    names = {p.stem for p in base.iterdir() if p.suffix in _SUFFIXES and p.is_file()}
    return sorted(names)


def _read_raw(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise WorkflowDefinitionError(f"{path.name}: invalid YAML: {exc}") from exc
    if raw is None:
        raise WorkflowDefinitionError(f"{path.name}: empty definition")
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError(f"{path.name}: top level must be a mapping")
    return raw


def load_definition(name: str) -> WorkflowDef:
    """Load and validate the workflow named ``name`` (its file stem).

    Raises ``WorkflowNotFoundError`` (listing available names) if no file matches,
    or ``WorkflowDefinitionError`` if the file is present but invalid.
    """
    path = _path_for(name)
    if path is None:
        raise WorkflowNotFoundError(f"workflow {name!r} not found; available: {_available_names()}")
    return parse_definition(_read_raw(path))


def list_definitions() -> list[dict[str, Any]]:
    """List available workflows with per-file validation status.

    Each entry: ``{"name", "valid", "error"}``. An invalid definition is reported
    (``valid=False`` + error summary), never raised — so listing a directory with a
    broken file does not crash.
    """
    out: list[dict[str, Any]] = []
    for name in _available_names():
        path = _path_for(name)
        assert path is not None
        entry: dict[str, Any] = {"name": name, "valid": True, "error": None}
        try:
            parse_definition(_read_raw(path))
        except WorkflowDefinitionError as exc:
            entry["valid"] = False
            entry["error"] = str(exc)
        out.append(entry)
    return out
