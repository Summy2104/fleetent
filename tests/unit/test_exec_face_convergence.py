"""Unit tests: run_code is the sole container-execution face (sandbox-exec-face).

No `sandbox_exec` (or any second tool that acquires a container + executes inside it)
may exist, and run_code keeps risk_level=medium so there is no lower-risk equivalent
execution bypass around the action-gate containment门控.
"""

from __future__ import annotations


def test_run_code_registered_medium_risk() -> None:
    import fleetent.tools.builtin_tools as _bt  # noqa: F401 — registers builtin tools
    from fleetent.tools import registry as tool_registry

    assert "run_code" in tool_registry._registry
    assert tool_registry.get_risk_level("run_code") == "medium"


def test_no_sandbox_exec_tool() -> None:
    import fleetent.tools  # noqa: F401 — triggers builtin tool registration side effect
    from fleetent.tools import registry as tool_registry

    names = set(tool_registry._registry)
    # No second container-internal execution face by name.
    assert "sandbox_exec" not in names
    # Defensive: nothing else looks like a sandbox-exec alias.
    assert not any("sandbox" in n and "exec" in n for n in names)


def test_run_code_is_only_sandbox_manager_consumer() -> None:
    # The only tool that acquires a container via SandboxManager is run_code: assert no
    # other registered builtin tool function references a SandboxManager.acquire path.
    import inspect

    import fleetent.tools  # noqa: F401
    from fleetent.tools import registry as tool_registry

    acquire_users = []
    for name, (fn, _schema) in tool_registry._registry.items():
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        if ".acquire(" in src or "_get_manager(" in src:
            acquire_users.append(name)
    assert acquire_users == ["run_code"]
