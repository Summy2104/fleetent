"""Sandbox integration public API.

The Docker-backed code-execution sandbox: a pluggable external execution backend
behind the ``run_code`` tool (sibling to ``integrations/mcp/``). Cross-package
callers import from here, not from the internal modules.
"""

from fleetent.integrations.sandbox.cleanup import cleanup_orphans
from fleetent.integrations.sandbox.client import ExecResult, SandboxClient
from fleetent.integrations.sandbox.config import (
    NetworkPolicy,
    SandboxLifecycle,
    SandboxResources,
    build_resources_by_scope,
    load_sandbox_lifecycle,
    load_sandbox_resources,
)
from fleetent.integrations.sandbox.enablement import (
    Mode,
    get_effective_mode,
    is_code_execution_enabled,
    load_sandbox_mode,
    resolve_effective_mode,
)
from fleetent.integrations.sandbox.maintenance import start_idle_sweep, stop_idle_sweep
from fleetent.integrations.sandbox.manager import SandboxManager, Scope
from fleetent.integrations.sandbox.output_truncation import truncate_stream
from fleetent.integrations.sandbox.redaction import redact_secrets
from fleetent.integrations.sandbox.secrets import build_sandbox_env, is_sensitive_name

__all__ = [
    "Mode",
    "NetworkPolicy",
    "SandboxClient",
    "ExecResult",
    "SandboxLifecycle",
    "SandboxManager",
    "SandboxResources",
    "Scope",
    "build_resources_by_scope",
    "build_sandbox_env",
    "cleanup_orphans",
    "get_effective_mode",
    "is_code_execution_enabled",
    "is_sensitive_name",
    "load_sandbox_lifecycle",
    "load_sandbox_mode",
    "load_sandbox_resources",
    "redact_secrets",
    "resolve_effective_mode",
    "start_idle_sweep",
    "stop_idle_sweep",
    "truncate_stream",
]
