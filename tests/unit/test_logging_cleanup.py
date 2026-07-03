from __future__ import annotations

import ast
from pathlib import Path

from fleetent.config import LoggingSettings, Settings


def test_logging_settings_drop_json_file_and_ignore_legacy_key() -> None:
    assert "json_file" not in LoggingSettings.model_fields

    settings = Settings(observability={"logging": {"json_file": False}})

    assert "json_file" not in settings.observability.logging.model_dump()


def test_all_uvicorn_entrypoints_set_log_level_explicitly() -> None:
    root = Path("src/fleetent")
    missing: list[str] = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_uvicorn_config = (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "uvicorn"
                and func.attr == "Config"
            )
            is_uvicorn_run = isinstance(func, ast.Name) and func.id == "uvicorn_run"
            if not (is_uvicorn_config or is_uvicorn_run):
                continue
            if any(keyword.arg == "log_level" for keyword in node.keywords):
                continue
            missing.append(f"{path.relative_to(root.parent)}:{node.lineno}")

    assert not missing, f"uvicorn entrypoints missing explicit log_level: {missing}"
