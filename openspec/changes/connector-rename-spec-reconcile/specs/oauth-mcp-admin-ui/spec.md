# oauth-mcp-admin-ui Specification

## MODIFIED Requirements

### Requirement: OAuth connectors tab
The admin console SHALL present an OAuth Connectors tab (distinct from the IM Connectors tab) listing external services registry entries with masked secrets from `GET /admin/connectors`, plus the per-user authorization (grants) matrix. Write controls SHALL be admin-only. HTTP 端点路径保持不变（向后兼容）。

#### Scenario: Admin sees services and grants
- **WHEN** an admin opens the OAuth Connectors tab
- **THEN** external services are listed via `GET /admin/connectors` (secrets masked) and grants via `GET /admin/connectors/grants`

#### Scenario: Viewer cannot mutate services
- **WHEN** a viewer opens the tab
- **THEN** create / edit / revoke controls are hidden

### Requirement: Connector CRUD and grant revoke
The console SHALL let an admin add and edit an external service config and revoke a user's grant.

#### Scenario: Revoke a grant
- **WHEN** an admin revokes a user's service grant
- **THEN** the console calls `POST /admin/connectors/grants/{user_id}/{connector_id}/revoke`
