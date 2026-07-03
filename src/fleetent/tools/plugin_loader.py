"""Plugin loader (AR7): the third tool source after builtin tools and MCP servers.

Enterprise teams extend the platform without touching its source: drop a
`plugins/{name}/` dir containing a `plugin.yaml` manifest and an `__init__.py`
with `@tool` functions. At startup the loader scans the injectable `PLUGINS_DIR`,
imports each `enabled: true` plugin package (triggering the `@tool` registration
side effect), then rewrites the freshly registered keys into the namespaced form
`{plugin_name}__{tool_name}` (double underscore, matching the MCP `{server}__{tool}`
convention). A malformed manifest or a failed import is logged and skipped — one
bad plugin never blocks startup, mirroring `mcp_client.register_all` /
`skill_registry.scan`.
"""

import importlib
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from fleetent.structured_logging import get_logger
from fleetent.tools import registry as tool_registry

logger = get_logger(__name__)


# Module-level path constant, injectable via monkeypatch (no-global-mutable-state
# rule). The loader reads `FLEETENT_PLUGINS_DIR` first, mirroring the env-override
# pattern of skill_registry (which uses FLEETENT_SKILLS_DIR).
PLUGINS_DIR: str = "./plugins"

_MANIFEST_NAME = "plugin.yaml"


@dataclass(frozen=True)
class PluginMeta:
    """Metadata for a loaded plugin, parsed from its plugin.yaml manifest."""

    name: str
    enabled: bool
    path: str
    version: str | None = None
    description: str | None = None


def _resolve_plugins_dir(plugins_dir: str | None) -> str:
    """Return the plugins directory: explicit arg > env override > module default."""
    if plugins_dir is not None:
        return plugins_dir
    return os.environ.get("FLEETENT_PLUGINS_DIR", PLUGINS_DIR)


def expand_plugin_patterns(plugins: list[str]) -> list[str]:
    """Expand agent `plugins` names into namespace wildcard patterns.

    `["crm_tools"]` -> `["crm_tools__*"]`. The result is merged into an agent's
    effective `allowed_tools` so the existing `agent_policy.check_tool_access`
    fnmatch filter (applied in agent_loop before exposing schemas to the LLM)
    admits exactly the authorised plugins' namespaced tools.
    """
    return [f"{name}__*" for name in plugins]


def _parse_manifest(manifest_path: Path) -> dict[str, object] | None:
    """Parse a plugin.yaml into a mapping, or None when invalid.

    None covers: unreadable file, malformed YAML, non-mapping top level, or a
    missing/empty `name`. The caller logs and skips on None.
    """
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(parsed, dict):
        return None
    name = parsed.get("name")
    if not isinstance(name, str) or not name:
        return None
    return parsed


def _namespace_new_keys(plugin_name: str, before: set[str], package: str) -> None:
    """Rewrite this plugin's freshly registered tool keys to the namespaced form.

    Only keys that (a) are new since `before` and (b) belong to a callable
    *defined inside this plugin package* (by `__module__` prefix) are renamed.
    This excludes tools that an `__init__.py` pulled in by indirectly importing a
    registration-side-effect module (e.g. `fleetent.tools`), so existing builtin /
    MCP keys are never reassigned into the plugin namespace (D1 / risk mitigation).

    A target name that already exists is skipped with a warning rather than
    overwriting an existing tool (D6).
    """
    registry = tool_registry._registry
    risk_levels = tool_registry._risk_levels
    for key in list(registry.keys()):
        if key in before:
            continue
        fn, schema = registry[key]
        owner = getattr(fn, "__module__", "") or ""
        if owner != package and not owner.startswith(f"{package}."):
            continue
        namespaced = f"{plugin_name}__{key}"
        if namespaced in registry:
            logger.warn(
                "plugin_tool_name_conflict",
                plugin=plugin_name,
                tool=namespaced,
                reason="namespaced name already registered",
            )
            continue
        schema["function"]["name"] = namespaced
        registry[namespaced] = (fn, schema)
        del registry[key]
        if key in risk_levels:
            risk_levels[namespaced] = risk_levels.pop(key)


def _reserved_namespaces() -> set[str]:
    """Namespace prefixes already in use: MCP server ids + builtin tool names.

    A plugin name must not collide with these or with another plugin (D6). MCP
    tools are keyed `{server_id}__{tool}`, so the server id is the prefix before
    the first `__`; builtin tools are keyed by bare function name (no `__`).
    """
    from fleetent.integrations.mcp import client as mcp_client

    # The registry is now keyed by (scope, server_id) after the MCP scope re-key;
    # the reserved namespace is the server id (second element), regardless of scope.
    reserved: set[str] = {server_id for _scope, server_id in mcp_client._server_registry}
    for key in tool_registry._registry:
        reserved.add(key.split("__", 1)[0] if "__" in key else key)
    return reserved


def _load_one(plugin_dir: Path, taken: set[str]) -> PluginMeta | None:
    """Load a single plugin dir; return its meta, or None when skipped.

    `taken` accumulates names claimed by already-loaded plugins (plus the reserved
    namespaces) so two plugins cannot claim the same name. Any per-plugin failure
    is logged at warning and returns None — never raises (D4).
    """
    manifest_path = plugin_dir / _MANIFEST_NAME
    parsed = _parse_manifest(manifest_path)
    if parsed is None:
        logger.warn(
            "plugin_manifest_invalid",
            path=str(plugin_dir),
            reason="missing/invalid YAML, non-mapping, or missing name",
        )
        return None

    name = str(parsed["name"])
    enabled = bool(parsed.get("enabled", False))
    meta = PluginMeta(
        name=name,
        enabled=enabled,
        path=str(plugin_dir),
        version=_as_opt_str(parsed.get("version")),
        description=_as_opt_str(parsed.get("description")),
    )
    if not enabled:
        return meta

    if name in taken:
        logger.warn(
            "plugin_namespace_conflict",
            plugin=name,
            reason="name collides with an MCP server, builtin namespace, or another plugin",
        )
        return None

    before = set(tool_registry._registry.keys())
    try:
        importlib.import_module(plugin_dir.name)
    except Exception as exc:  # noqa: BLE001 — logged then skipped, not swallowed (D4)
        logger.warn("plugin_import_failed", name=name, exception=exc)
        return None

    _namespace_new_keys(name, before, plugin_dir.name)
    taken.add(name)
    return meta


def load_plugins(plugins_dir: str | None = None) -> list[PluginMeta]:
    """Scan the plugins directory, loading every `enabled: true` plugin.

    For each immediate subdirectory that contains a `plugin.yaml`, the manifest is
    parsed and (when enabled) the package is imported and its newly registered
    tools are namespaced as `{plugin_name}__{tool_name}`. A missing directory
    yields an empty list. Malformed manifests, failed imports, and namespace
    conflicts are logged and skipped without aborting the scan (D4 / D6).

    Returns the metadata for every plugin whose manifest parsed (enabled or not),
    so callers can introspect what was discovered.
    """
    base = Path(_resolve_plugins_dir(plugins_dir))
    if not base.is_dir():
        return []

    metas: list[PluginMeta] = []
    taken = _reserved_namespaces()
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if not (child / _MANIFEST_NAME).is_file():
            continue
        meta = _load_one(child, taken)
        if meta is not None:
            metas.append(meta)
    return metas


def _as_opt_str(value: object) -> str | None:
    """Normalize a scalar/missing manifest value into an optional string."""
    if value is None:
        return None
    return str(value)
