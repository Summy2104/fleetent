## ADDED Requirements

### Requirement: MCP servers managed natively in the React SPA

The React admin SPA SHALL render MCP servers natively (within the Connectors domain, not a deep-link to legacy) and SHALL support the full lifecycle against the existing admin API: list, create, **edit**, **delete**, **test**, reconnect, view tools, and run doctor. This closes the legacy create-only gap.

#### Scenario: Edit, delete, and test an MCP server

- **WHEN** an admin edits an existing MCP server and saves, deletes one (with confirmation), or tests one
- **THEN** the SPA calls `PUT /admin/mcp/servers/{id}` / `DELETE /admin/mcp/servers/{id}` / `POST /admin/mcp/servers/{id}/test` and reflects the result

#### Scenario: View tools and reconnect

- **WHEN** an admin lists an MCP server's tools or reconnects it
- **THEN** the SPA calls `GET /admin/mcp/servers/{id}/tools` (resp. `POST /admin/mcp/servers/{id}/reconnect`) and shows the outcome
