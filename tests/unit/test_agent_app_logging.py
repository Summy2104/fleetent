"""Unit tests for agent_app.boot() logging configuration from agent.yaml.

Verifies that the standalone agent runtime applies log_format and
observability.logging.* from agent.yaml at boot time, without affecting
the platform server path (which reads from Settings).
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml


def _write_agent_yaml(home: Path, log_format: str = "console") -> None:
    agent_yaml = {
        "name": home.name,
        "version": 1,
        "models": {
            "targets": [
                {
                    "id": "default",
                    "provider": "local",
                    "protocol": "openai_chat",
                    "base_url": "http://localhost:11434/v1/",
                    "model": "default",
                }
            ],
            "routes": {"default": [{"target": "default"}]},
        },
        "log_format": log_format,
        "observability": {
            "logging": {
                "console_level": "warning",
                "file_level": "info",
                "directory": "data/logs",
            }
        },
    }
    (home / "agent.yaml").write_text(yaml.dump(agent_yaml))


def _make_stack(stack: contextlib.ExitStack) -> dict[str, MagicMock]:
    """Enter all required boot() mocks and return the mock map."""
    mocks: dict[str, MagicMock] = {}
    mocks["infra"] = stack.enter_context(
        patch("fleetent.runtime.agent_app._start_infra", AsyncMock())
    )
    mocks["scan_skills"] = stack.enter_context(patch("fleetent.skills.scan"))
    mocks["load_plugins"] = stack.enter_context(patch("fleetent.tools.plugin_loader.load_plugins"))
    mocks["vector_store"] = stack.enter_context(
        patch("fleetent.vector_store.configure_from_active_agent")
    )
    return mocks


def _mock_supervisor() -> MagicMock:
    sup = MagicMock()
    sup.start = AsyncMock()
    sup.stop_all = AsyncMock()
    return sup


async def test_boot_configures_logging_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """boot() with log_format: json calls configure_structured_logging with agent's settings."""
    home = tmp_path / "myagent"
    home.mkdir()
    _write_agent_yaml(home, log_format="json")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    with contextlib.ExitStack() as stack:
        _make_stack(stack)
        mock_csl = stack.enter_context(
            patch("fleetent.structured_logging.configure_structured_logging")
        )
        mock_structlog = stack.enter_context(patch("structlog.configure"))

        from fleetent.runtime import agent_app

        await agent_app.boot(
            "myagent",
            home=home,
            start_im=False,
            with_infra=False,
            supervisor=_mock_supervisor(),
            telegram_supervisor=_mock_supervisor(),
        )

    mock_csl.assert_called_once()
    call_kwargs = mock_csl.call_args.kwargs
    assert call_kwargs["console_level"] == "warning"
    assert call_kwargs["file_level"] == "info"
    mock_structlog.assert_called_once()
    structlog_kwargs = mock_structlog.call_args.kwargs
    import structlog as sl

    assert isinstance(structlog_kwargs["processors"][-1], sl.processors.JSONRenderer)


async def test_boot_configures_logging_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """boot() with log_format: console should use ConsoleRenderer."""
    home = tmp_path / "consoleagent"
    home.mkdir()
    _write_agent_yaml(home, log_format="console")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    with contextlib.ExitStack() as stack:
        _make_stack(stack)
        mock_csl = stack.enter_context(
            patch("fleetent.structured_logging.configure_structured_logging")
        )
        mock_structlog = stack.enter_context(patch("structlog.configure"))

        from fleetent.runtime import agent_app

        await agent_app.boot(
            "consoleagent",
            home=home,
            start_im=False,
            with_infra=False,
            supervisor=_mock_supervisor(),
            telegram_supervisor=_mock_supervisor(),
        )

    mock_csl.assert_called_once()
    mock_structlog.assert_called_once()
    structlog_kwargs = mock_structlog.call_args.kwargs
    import structlog as sl

    assert isinstance(structlog_kwargs["processors"][-1], sl.dev.ConsoleRenderer)


def _write_agent_yaml_blank_log_dir(home: Path) -> None:
    agent_yaml = {
        "name": home.name,
        "version": 1,
        "models": {
            "targets": [
                {
                    "id": "default",
                    "provider": "local",
                    "protocol": "openai_chat",
                    "base_url": "http://localhost:11434/v1/",
                    "model": "default",
                }
            ],
            "routes": {"default": [{"target": "default"}]},
        },
        "observability": {"logging": {"directory": ""}},
    }
    (home / "agent.yaml").write_text(yaml.dump(agent_yaml))


async def test_blank_log_directory_resolves_to_agent_home_data_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """blank directory in agent.yaml → logs go to agents/<id>/data/logs/."""
    home = tmp_path / "logagent"
    home.mkdir()
    _write_agent_yaml_blank_log_dir(home)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    with contextlib.ExitStack() as stack:
        _make_stack(stack)
        mock_csl = stack.enter_context(
            patch("fleetent.structured_logging.configure_structured_logging")
        )
        stack.enter_context(patch("structlog.configure"))

        from fleetent.runtime import agent_app

        await agent_app.boot(
            "logagent",
            home=home,
            start_im=False,
            with_infra=False,
            supervisor=_mock_supervisor(),
            telegram_supervisor=_mock_supervisor(),
        )

    mock_csl.assert_called_once()
    assert mock_csl.call_args.kwargs["directory"] == home / "data" / "logs"


async def test_explicit_log_directory_used_as_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """explicit directory in agent.yaml is forwarded unchanged."""
    home = tmp_path / "explicitagent"
    home.mkdir()
    # Use the existing helper that sets directory: "data/logs"
    _write_agent_yaml(home, log_format="console")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    with contextlib.ExitStack() as stack:
        _make_stack(stack)
        mock_csl = stack.enter_context(
            patch("fleetent.structured_logging.configure_structured_logging")
        )
        stack.enter_context(patch("structlog.configure"))

        from fleetent.runtime import agent_app

        await agent_app.boot(
            "explicitagent",
            home=home,
            start_im=False,
            with_infra=False,
            supervisor=_mock_supervisor(),
            telegram_supervisor=_mock_supervisor(),
        )

    mock_csl.assert_called_once()
    assert mock_csl.call_args.kwargs["directory"] == "data/logs"
