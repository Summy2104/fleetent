# mcp-client-compliance Specification

## Purpose
TBD - created by archiving change mcp-client-compliance. Update Purpose after archive.
## Requirements
### Requirement: Complete tool discovery via pagination

When discovering tools via `tools/list`, the MCP client SHALL follow the `nextCursor` field and continue requesting subsequent pages until no cursor is returned, aggregating tools across all pages. This SHALL apply to both the http and stdio transports and to both startup registration and the admin connectivity probe. The client SHALL bound the number of pages it will fetch to avoid an unbounded loop if a server returns a non-terminating cursor.

#### Scenario: Multi-page tool list fully registered
- **WHEN** a server's `tools/list` returns a first page with a `nextCursor` and a second page without one
- **THEN** the client registers the tools from both pages

#### Scenario: Single-page tool list unchanged
- **WHEN** a server's `tools/list` returns tools and no `nextCursor`
- **THEN** the client issues a single `tools/list` request and registers exactly those tools

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

### Requirement: Protocol version negotiation and header echo

On `initialize`, the client SHALL capture the server-returned `protocolVersion` into per-server state, defaulting to the client's protocol version when the server omits it. For the http transport, requests issued after a session is established SHALL carry an `MCP-Protocol-Version` header set to the captured version. The per-server protocol version SHALL NOT live in module-level mutable global state.

#### Scenario: Negotiated version echoed on subsequent requests
- **WHEN** an http server's `initialize` response reports a `protocolVersion`
- **THEN** that server's subsequent `tools/list` and `tools/call` requests carry an `MCP-Protocol-Version` header equal to the reported version

#### Scenario: Version defaults when server omits it
- **WHEN** an http server's `initialize` response does not report a `protocolVersion`
- **THEN** the client uses its own protocol version for the captured value and the header

### Requirement: Server capability capture

On `initialize`, the client SHALL capture the server-advertised `capabilities` into per-server state (held per server, never in module-level mutable global state), so downstream features can gate on what a server supports.

#### Scenario: Capabilities captured from initialize
- **WHEN** a server's `initialize` response advertises a `capabilities` object
- **THEN** that server's captured capabilities reflect the advertised object

#### Scenario: Absent capabilities default to empty
- **WHEN** a server's `initialize` response omits `capabilities`
- **THEN** the server's captured capabilities are an empty mapping rather than unset

