from __future__ import annotations

import ast
import importlib
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog

import fleetent.logging_setup as logging_setup


def _reload_logging_setup() -> None:
    importlib.reload(logging_setup)


def test_setup_process_logging_configures_console_renderer(tmp_path: Path) -> None:
    _reload_logging_setup()

    with (
        patch("fleetent.logging_setup.configure_structured_logging") as configure_structured,
        patch("structlog.configure") as configure_structlog,
        patch("logging.basicConfig") as basic_config,
    ):
        logging_setup.setup_process_logging(
            console_level="warn",
            file_level="trace",
            directory=tmp_path,
            log_format="console",
        )

    configure_structured.assert_called_once_with(
        console_level="warn",
        file_level="trace",
        directory=tmp_path,
    )
    structlog_kwargs = configure_structlog.call_args.kwargs
    assert isinstance(structlog_kwargs["processors"][-1], structlog.dev.ConsoleRenderer)
    basic_kwargs = basic_config.call_args.kwargs
    assert basic_kwargs["format"] == "%(message)s"
    assert basic_kwargs["level"] == logging.INFO
    assert len(basic_kwargs["handlers"]) == 1
    assert isinstance(basic_kwargs["handlers"][0], logging.StreamHandler)


def test_setup_process_logging_configures_json_renderer(tmp_path: Path) -> None:
    _reload_logging_setup()

    with (
        patch("fleetent.logging_setup.configure_structured_logging"),
        patch("structlog.configure") as configure_structlog,
        patch("logging.basicConfig"),
    ):
        logging_setup.setup_process_logging(
            console_level="info",
            file_level="debug",
            directory=tmp_path,
            log_format="json",
        )

    assert isinstance(
        configure_structlog.call_args.kwargs["processors"][-1],
        structlog.processors.JSONRenderer,
    )


def test_setup_process_logging_log_level_env_overrides_console_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reload_logging_setup()
    monkeypatch.setenv("LOG_LEVEL", "debug")

    with (
        patch("fleetent.logging_setup.configure_structured_logging") as configure_structured,
        patch("structlog.configure"),
        patch("logging.basicConfig"),
    ):
        logging_setup.setup_process_logging(
            console_level="info",
            file_level="warn",
            directory=tmp_path,
            log_format="console",
        )

    configure_structured.assert_called_once_with(
        console_level="debug",
        file_level="warn",
        directory=tmp_path,
    )


def test_setup_process_logging_rejects_invalid_log_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reload_logging_setup()
    monkeypatch.setenv("LOG_LEVEL", "verbose")

    with pytest.raises(ValueError, match="silent, fatal, error, warn, info, debug, trace"):
        logging_setup.setup_process_logging(directory=tmp_path)


def test_logging_setup_is_the_only_structlog_and_basicconfig_site() -> None:
    root = Path("src/fleetent")
    structlog_config_sites: list[str] = []
    basic_config_sites: list[str] = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "structlog"
                and func.attr == "configure"
            ):
                structlog_config_sites.append(str(path.relative_to(root.parent)))
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "logging"
                and func.attr == "basicConfig"
            ):
                basic_config_sites.append(str(path.relative_to(root.parent)))

    assert structlog_config_sites == ["fleetent/logging_setup.py"]
    assert basic_config_sites == ["fleetent/logging_setup.py"]
