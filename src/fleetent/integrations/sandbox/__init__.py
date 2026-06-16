"""Sandbox integration public API.

The code-execution sandbox: a pluggable external execution backend behind the
``run_code`` tool (sibling to ``integrations/mcp/``), with Docker and microsandbox
backends selected by configuration. Cross-package callers import from here, not
from the internal modules.
"""

from fleetent.integrations.sandbox.backend import (
    BackendCapabilities,
    BaseSandboxBackend,
    ExecResult,
    SkillMount,
)
from fleetent.integrations.sandbox.backends.docker import DockerBackend
from fleetent.integrations.sandbox.backends.microsandbox import MicrosandboxBackend
from fleetent.integrations.sandbox.cleanup import cleanup_orphans
from fleetent.integrations.sandbox.client import SandboxClient
from fleetent.integrations.sandbox.config import (
    NetworkPolicy,
    SandboxResources,
    SkillMountConfig,
    resources_from_agent_settings,
)
from fleetent.integrations.sandbox.enablement import (
    Mode,
    get_effective_mode,
    is_code_execution_enabled,
    load_sandbox_mode,
    resolve_effective_mode,
)
from fleetent.integrations.sandbox.maintenance import start_idle_sweep, stop_idle_sweep
from fleetent.integrations.sandbox.manager import SandboxManager, Scope, WorkspaceScope
from fleetent.integrations.sandbox.output_spill import cap_or_spill
from fleetent.integrations.sandbox.output_truncation import truncate_stream
from fleetent.integrations.sandbox.redaction import redact_secrets
from fleetent.integrations.sandbox.secrets import build_sandbox_env, is_sensitive_name
from fleetent.integrations.sandbox.workspace_gc import (
    gc_agent_workspace,
    gc_session_workspace,
)

__all__ = [
    "BackendCapabilities",
    "BaseSandboxBackend",
    "DockerBackend",
    "MicrosandboxBackend",
    "Mode",
    "NetworkPolicy",
    "SandboxClient",
    "ExecResult",
    "SandboxManager",
    "SandboxResources",
    "Scope",
    "WorkspaceScope",
    "SkillMount",
    "SkillMountConfig",
    "resources_from_agent_settings",
    "build_sandbox_env",
    "cap_or_spill",
    "cleanup_orphans",
    "gc_agent_workspace",
    "gc_session_workspace",
    "get_effective_mode",
    "is_code_execution_enabled",
    "is_sensitive_name",
    "load_sandbox_mode",
    "redact_secrets",
    "resolve_effective_mode",
    "start_idle_sweep",
    "stop_idle_sweep",
    "truncate_stream",
]
