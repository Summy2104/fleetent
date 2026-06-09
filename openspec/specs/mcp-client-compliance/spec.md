# mcp-client-compliance Specification

## Purpose
TBD - created by archiving change mcp-client-compliance. Update Purpose after archive.
## Requirements
### Requirement: Complete tool discovery via pagination

When discovering tools via `tools/list`, the client SHALL drive pagination through the SDK `ClientSession.list_tools(cursor=...)`, following the returned `nextCursor` until none remains and aggregating tools across all pages. This SHALL apply to all transports (stdio, http, sse) and to both startup registration and the admin connectivity probe. The client SHALL bound the number of pages it will fetch to avoid an unbounded loop if a server returns a non-terminating cursor.

#### Scenario: Multi-page tool list fully registered
- **WHEN** a server's `tools/list` returns a first page with a `nextCursor` and a second page without one
- **THEN** the client registers the tools from both pages via successive `ClientSession.list_tools(cursor=...)` calls

#### Scenario: Single-page tool list unchanged
- **WHEN** a server's `tools/list` returns tools and no `nextCursor`
- **THEN** the client issues a single `list_tools` call and registers exactly those tools

#### Scenario: Non-terminating cursor is bounded
- **WHEN** a server keeps returning a `nextCursor` on every page
- **THEN** the client stops after a bounded number of pages rather than looping forever

### Requirement: Provider-safe input schema normalization

Before registering an MCP tool, the client SHALL normalize the server-provided input schema so it is safe for LLM providers, without changing its meaning. The client SHALL ensure the top-level schema declares `type: "object"` and contains a `properties` object. The client SHALL rename a `definitions` block to `$defs` and rewrite `#/definitions/...` references to `#/$defs/...` accordingly. The normalization SHALL NOT raise on unexpected schema shapes.

#### Scenario: Missing top-level type is defaulted
- **WHEN** an MCP tool's input schema omits `type` and `properties`
- **THEN** the registered tool's parameters declare `type: "object"` with a `properties` object

#### Scenario: definitions rewritten to $defs with refs updated
- **WHEN** an MCP tool's input schema uses a `definitions` block and a `#/definitions/Foo` reference
- **THEN** the registered schema uses `$defs` and the reference becomes `#/$defs/Foo`

#### Scenario: Already-valid schema preserved
- **WHEN** an MCP tool's input schema already declares `type: "object"` with `properties` and uses `$defs`
- **THEN** the registered schema is unchanged in meaning

### Requirement: Protocol version handled by the SDK

The client SHALL NOT hand-pin or hand-negotiate the MCP protocol version. The protocol version advertised on `initialize` and echoed on subsequent http requests SHALL be the SDK's `mcp.types.LATEST_PROTOCOL_VERSION`, with negotiation and the `MCP-Protocol-Version` header handled inside the SDK `ClientSession` / transport. No module-level hand-pinned version constant SHALL remain.

#### Scenario: Version comes from the SDK
- **WHEN** the client establishes a session with any MCP server
- **THEN** the protocol version used is the SDK's `LATEST_PROTOCOL_VERSION`, not a fleetent-hand-pinned constant, and version negotiation / header echo are performed by the SDK

### Requirement: Server capability capture

On session establishment, the client SHALL capture the server-advertised `capabilities` from the SDK `InitializeResult` into per-server state (held per server, never in module-level mutable global state), so downstream features can gate on what a server supports.

#### Scenario: Capabilities captured from initialize
- **WHEN** a server's session is established and its `InitializeResult` advertises a `capabilities` object
- **THEN** that server's captured capabilities reflect the advertised object

#### Scenario: Absent capabilities default to empty
- **WHEN** a server's `InitializeResult` omits `capabilities`
- **THEN** the server's captured capabilities are an empty mapping rather than unset

