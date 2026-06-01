## Why

`configuration-foundation` moved MCP server definitions into `config/settings.yaml` under
`mcp.servers`, but MCP servers are closer to runtime-managed integration registrations than ordinary
deployment-level settings. A deployment may have many MCP servers, operators may need to add or disable
servers independently, and a later MCP registry can reasonably move these definitions to SQLite.

Keeping server definitions inside `settings.yaml` makes the unified app settings file too broad and creates
the wrong long-term boundary. We should split MCP server definitions back out now, while keeping the old
`config/mcp.yaml` path retired to avoid reintroducing legacy behavior.

## What Changes

- Keep `config/settings.yaml` as the unified non-secret app settings file.
- Keep only MCP global policy in `settings.yaml` under `mcp`, such as `enabled`.
- Move MCP server definitions out of `settings.yaml` into a dedicated `config/mcp.servers.yaml` file.
- Continue to reject legacy `config/mcp.yaml` with a fail-fast startup error.
- Remove `mcp.servers` from `config/settings.yaml.example`.
- Add `config/mcp.servers.yaml.example` for static MCP server definitions.
- Update MCP docs and specs to describe the split.

## Out of Scope

- No backward compatibility for `config/mcp.yaml`.
- No runtime API, Admin UI, hot reload, or SQLite-backed MCP registry in this change.
- No changes to MCP tool naming or dispatch behavior.
- No migration of existing local untracked operator files.

## Module Boundary Impact

- **Owning package**: `platform` / MCP integration startup via existing `fleetent.mcp_client` and
  `fleetent.server` wiring.
- **Public API surface**: keep `mcp_client.register_all(servers: list[McpServerConfig])`; add or expose a
  focused loader for `config/mcp.servers.yaml` if needed by startup/tests.
- **Owned tables**: none.
- **Config namespace**: `settings.yaml` keeps `mcp` global policy; server definitions move to
  `config/mcp.servers.yaml`.
- **Cross-module dependencies**: server startup reads settings and MCP server definitions, then calls
  `mcp_client.register_all`.
- **Migration / shim plan**: no shim for `config/mcp.yaml`; `mcp.servers` in `settings.yaml` is removed
  because this is still MVP-stage configuration and we do not want to preserve the short-lived wrong shape.
