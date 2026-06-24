"""Unit tests for _redirect_agent_data_paths: per-agent data path wiring in boot()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest


def test_redirect_sets_sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.runtime import agent_app
    from fleetent.session import manager as session_mgr

    home = tmp_path / "myagent"
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", session_mgr.SESSIONS_DIR)

    agent_app._redirect_agent_data_paths(home)

    assert home / "data" / "sessions" == session_mgr.SESSIONS_DIR


def test_redirect_sets_approvals_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.im_gateway import access
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(access, "APPROVALS_PATH", access.APPROVALS_PATH)

    agent_app._redirect_agent_data_paths(home)

    assert home / "data" / "im_approvals.json" == access.APPROVALS_PATH


def test_redirect_updates_diagnostics_default_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.observability import diagnostics
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(diagnostics, "_default_data_dir", diagnostics._default_data_dir)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    agent_app._redirect_agent_data_paths(home)

    assert diagnostics._default_data_dir() == home / "data"


def test_redirect_sets_trace_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent import eval_logger
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(eval_logger, "TRACE_PATH", eval_logger.TRACE_PATH)

    agent_app._redirect_agent_data_paths(home)

    assert home / "data" / "traces.jsonl" == eval_logger.TRACE_PATH


def test_redirect_sets_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.integrations.sandbox import manager as sandbox_manager
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(sandbox_manager, "_WORKSPACE_ROOT", None)

    agent_app._redirect_agent_data_paths(home)

    assert sandbox_manager.workspace_root() == home / "data" / "workspaces"


def test_redirect_sets_tool_spillover_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.runtime import agent_app
    from fleetent.tools import result_truncation

    home = tmp_path / "myagent"
    monkeypatch.setattr(
        result_truncation,
        "SPILLOVER_DIR",
        result_truncation.SPILLOVER_DIR,
    )

    agent_app._redirect_agent_data_paths(home)

    assert home / "data" / "tool_spillover" == result_truncation.SPILLOVER_DIR


def test_redirect_sets_sandbox_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.integrations.sandbox import output_spill
    from fleetent.runtime import agent_app

    home = tmp_path / "myagent"
    monkeypatch.setattr(
        output_spill,
        "SANDBOX_OUTPUT_DIR",
        output_spill.SANDBOX_OUTPUT_DIR,
    )

    agent_app._redirect_agent_data_paths(home)

    assert home / "data" / "sandbox_output" == output_spill.SANDBOX_OUTPUT_DIR


async def test_minimal_boot_writes_runtime_files_only_under_agent_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import agent_config, eval_logger, vector_store
    from fleetent.integrations.sandbox import manager as sandbox_manager
    from fleetent.integrations.sandbox import output_spill
    from fleetent.runtime import agent_app
    from fleetent.skills import registry as skill_registry
    from fleetent.tools import plugin_loader, result_truncation

    fleetent_home = tmp_path / "fleetent-home"
    agent_home = fleetent_home / "tenants" / "default" / "agents" / "support"
    monkeypatch.setenv("FLEETENT_HOME", str(fleetent_home))
    monkeypatch.setattr(eval_logger, "TRACE_PATH", eval_logger.TRACE_PATH)
    monkeypatch.setattr(sandbox_manager, "_WORKSPACE_ROOT", None)
    monkeypatch.setattr(result_truncation, "SPILLOVER_DIR", result_truncation.SPILLOVER_DIR)
    monkeypatch.setattr(output_spill, "SANDBOX_OUTPUT_DIR", output_spill.SANDBOX_OUTPUT_DIR)
    monkeypatch.setattr(vector_store, "configure_from_active_agent", lambda: None)
    monkeypatch.setattr(skill_registry, "scan", lambda skills_dir=None: None)
    monkeypatch.setattr(plugin_loader, "load_plugins", lambda: None)
    monkeypatch.setattr(
        agent_config,
        "scan_home",
        lambda _: agent_config.AgentFile(
            name="support",
            version=1,
            models=agent_config.default_models(),
        ),
    )

    await agent_app.boot(
        "support",
        home=agent_home,
        supervisor=AsyncMock(),
        telegram_supervisor=AsyncMock(),
        start_im=False,
        with_infra=False,
    )

    eval_logger.log_run("hello", "world", [], 0.01)
    result_truncation.truncate_tool_result("x" * 100, max_bytes=10)
    output_spill.cap_or_spill("y" * 100, 10, label="stdout")
    sandbox_manager.host_workspace_dir("session:abc").mkdir(parents=True)

    root_data = fleetent_home / "data"
    assert not root_data.exists()
    assert (agent_home / "data" / "traces.jsonl").is_file()
    assert any((agent_home / "data" / "tool_spillover").iterdir())
    assert any((agent_home / "data" / "sandbox_output").iterdir())
    assert (agent_home / "data" / "workspaces").is_dir()
