from __future__ import annotations

import ast
from pathlib import Path

# Frozen ratchet baseline for stdlib ``logging.getLogger`` call sites in ``src``.
# This set may only shrink: when a file is migrated off stdlib logging, remove it here.
_KNOWN_STDLIB_LOGGER_FILES: frozenset[str] = frozenset(
    {
        "fleetent/agent_store.py",
        "fleetent/cron_scheduler.py",
        "fleetent/governance/approval_policy.py",
        "fleetent/governance/permission_gate.py",
        "fleetent/governance/user_input_gate.py",
        "fleetent/integrations/mcp/authorization.py",
        "fleetent/integrations/mcp/client.py",
        "fleetent/integrations/mcp/credential_submission.py",
        "fleetent/integrations/mcp/per_user_tokens.py",
        "fleetent/integrations/mcp/standalone_callback.py",
        "fleetent/integrations/mcp/standalone_credential.py",
        "fleetent/knowledge_base/standalone_sweep.py",
        "fleetent/memory/facts_commit.py",
        "fleetent/memory/facts_lifecycle.py",
        "fleetent/memory/facts_pipeline.py",
        "fleetent/memory/facts_search.py",
        "fleetent/platform/node_management/node_addressing.py",
        "fleetent/platform/node_management/node_desired_state_api.py",
        "fleetent/platform/node_management/node_store.py",
        "fleetent/platform/skill_management/git_source_store.py",
        "fleetent/platform/skill_management/pool_git.py",
        "fleetent/platform/skill_management/pool_sync.py",
        "fleetent/platform/webhook_management/webhook_inbound_api.py",
        "fleetent/runtime/approval_resume.py",
        "fleetent/schema_migrations.py",
        "fleetent/server.py",
        "fleetent/tools/builtin_tools.py",
        "fleetent/tools/file_tools.py",
        "fleetent/tools/interaction_tools.py",
        "fleetent/tools/registry.py",
        "fleetent/tools/shell_tool.py",
        "fleetent/tools/web_tools.py",
        "fleetent/vector_store/runtime.py",
    }
)


def test_structlog_imports_only_exist_in_logging_setup() -> None:
    root = Path("src/fleetent")
    structlog_imports: list[str] = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == "structlog" for alias in node.names):
                    structlog_imports.append(str(path.relative_to(root.parent)))
            elif isinstance(node, ast.ImportFrom) and node.module == "structlog":
                structlog_imports.append(str(path.relative_to(root.parent)))

    assert structlog_imports == ["fleetent/logging_setup.py"]


def test_stdlib_logging_getlogger_sites_do_not_grow() -> None:
    root = Path("src/fleetent")
    actual: set[str] = set()

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "logging"
                and func.attr == "getLogger"
            ):
                actual.add(str(path.relative_to(root.parent)))
                break

    assert actual <= _KNOWN_STDLIB_LOGGER_FILES, (
        "New stdlib logging.getLogger sites detected: "
        f"{sorted(actual - _KNOWN_STDLIB_LOGGER_FILES)}"
    )


def test_logger_calls_do_not_stringify_exceptions() -> None:
    root = Path("src/fleetent")
    violations: list[str] = []
    logger_methods = {"error", "warn", "warning", "fatal", "critical", "exception"}

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in {"logger", "_logger"}
                and func.attr in logger_methods
            ):
                continue
            for keyword in node.keywords:
                if keyword.arg != "error":
                    continue
                value = keyword.value
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "str"
                ):
                    violations.append(
                        f"{path.relative_to(root.parent)}:{node.lineno}:{func.value.id}.{func.attr}"
                    )

    assert not violations, "Replace error=str(...) in logger calls: " + ", ".join(violations)
