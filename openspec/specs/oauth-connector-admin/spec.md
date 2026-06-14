# oauth-connector-admin Specification

## Purpose
TBD - created by archiving change 2026-06-02-connector-management. Update Purpose after archive.
## Requirements
### Requirement: Connector directory and configuration

An admin SHALL be able to list all declared external services and create / edit / delete a service configuration without changing core code. In main, this requirement is served by `/admin/connectors`; this phase SHALL keep that route for compatibility while rewiring it to the landed `external_service_store`. Each entry SHALL show the P0-backed registry fields already persisted on main: `service_id`（or legacy response alias `id`）、`display_name`、`protocol`（`oauth2` | `apikey`）、`oauth_config`（authorize/token endpoints、scopes、`client_id` 等非密字段）和 `enabled`。The directory SHALL be a single global registry —— 无 owning-agent 列，`agent_id` 过滤参数不得改变结果（承接 P0 移除的 per-agent 覆盖层）。`client_secret` SHALL never be returned in plaintext。仅 admin 可写，viewer 只读。

#### Scenario: List services with masked secret and protocol
- **WHEN** an admin or viewer opens the external services directory
- **THEN** each entry shows the service id, `display_name`, `protocol`, and non-secret `oauth_config` fields, and `client_secret` is masked / omitted and never returned in plaintext

#### Scenario: Add an OAuth service takes effect
- **WHEN** an admin creates a new `protocol="oauth2"` service and saves
- **THEN** 该服务出现在目录中，无需改核心代码或重启即可被授权使用

#### Scenario: Add an API-key service takes effect
- **WHEN** an admin creates a new `protocol="apikey"` service and saves
- **THEN** 该服务以 `protocol=apikey` 出现在目录中

#### Scenario: Viewer cannot edit configuration
- **WHEN** a viewer attempts to create / edit / delete a service configuration
- **THEN** the request is rejected with 403 and the directory remains read-only for viewers

#### Scenario: Agent filter is inert for the global registry
- **WHEN** an admin calls the directory with an `agent_id` query parameter
- **THEN** the result set is unchanged because the registry is global-only

#### Scenario: Delete a service
- **WHEN** an admin deletes a service and confirms
- **THEN** 该服务从目录移除，操作落审计

### Requirement: Per-user authorization matrix
The admin face SHALL present a `(user, connector)` authorization matrix whose per-cell
state aligns with the `connectors` domain query result: not-authorized (`NeedsConsent`,
never granted), authorized (valid credential, with granted scopes), needs-reauthorization
(`NeedsConsent`, refresh token expired), and credential-error (`CredentialError`, refresh
network failure, retryable). Matrix queries SHALL be scoped to the connector's owning
agent so authorization for an agent-owned connector is never conflated with a global
default or another agent's connector of the same id. The matrix SHALL be viewable by user
or by connector. State determination is delegated to the `connectors` domain and SHALL
NOT be recomputed here.

#### Scenario: Mixed authorization states shown (场景 109)
- **WHEN** an admin filters the matrix to a user who has authorized `google-drive`, never authorized `github`, and whose `notion` refresh token has expired
- **THEN** `google-drive` shows authorized with its scopes, `github` shows not-authorized, and `notion` shows "needs reauthorization"

#### Scenario: Credential error distinguished from needs-consent
- **WHEN** the `connectors` query returns `CredentialError` for a `(user, connector)` pair
- **THEN** the cell shows "credential error (retryable)" distinctly from "not-authorized" and "needs reauthorization"

#### Scenario: Switch matrix viewpoint
- **WHEN** an admin toggles between the by-user and by-connector views
- **THEN** the same authorization data is re-aggregated under the selected axis

#### Scenario: Authorization scoped to owning agent
- **WHEN** agent `billing` and agent `sales` each own a `github` connector and a user
  has authorized only `billing`'s
- **THEN** the matrix shows the user authorized for `billing`'s `github` and
  not-authorized for `sales`'s `github`

### Requirement: Admin cannot complete first-time consent on behalf of a user
The admin face SHALL NOT provide any path to complete a user's first-time OAuth consent. OAuth consent requires the user's own browser redirect. No delegate-consent endpoint SHALL exist.

#### Scenario: No delegate-consent entry for unauthorized cell (场景 110)
- **WHEN** an admin opens an unauthorized `(user, connector)` cell (e.g. Bob has never authorized `github`)
- **THEN** the UI offers no "authorize on behalf of" action and clearly states that first-time consent must be completed by the user's own browser redirect; no delegate-consent endpoint accepts the request

### Requirement: Admin revoke on behalf of a user
An admin SHALL be able to revoke a `(user, connector)` grant. The revoke semantics (delete credential, call the external revoke endpoint) are delegated to the `connectors` domain; this face only triggers it, requires confirmation, and audits it. After revoke the user returns to `NeedsConsent` on next use of that tool.

#### Scenario: Revoke with confirmation and audit (场景 111)
- **WHEN** an admin revokes `(Alice, google-drive)` and confirms the high-risk action
- **THEN** the `connectors` domain deletes the credential and calls the external revoke endpoint, Alice must re-authorize on next use, and the revoke is written to the audit log

#### Scenario: Revoke requires admin
- **WHEN** a viewer attempts to revoke a `(user, connector)` grant
- **THEN** the request is rejected with 403

### Requirement: Offboarding linkage visibility
The admin face SHALL display the result of the `connectors` domain auto-revoking all of a user's connector credentials when user-center disables that user, including which connectors were revoked and whether each succeeded, for offboarding audit.

#### Scenario: Show offboarding revoke result
- **WHEN** a user has been disabled in user-center and the admin opens that user's connector view
- **THEN** the face shows each connector whose credential was auto-revoked by the linkage and the success/failure of each external revoke

### Requirement: Credential lifecycle observability
The admin face SHALL show, per connector, access-token auto-refresh success/failure rate and the count of re-authorizations caused by refresh-token expiry, to diagnose why a connector repeatedly requires re-authorization.

#### Scenario: Per-connector refresh metrics
- **WHEN** an admin opens the lifecycle view for a connector
- **THEN** it shows the auto-refresh success/failure rate and the re-authorization count for that connector

### Requirement: Sensitive value masking across all views
Every connector view and audit entry SHALL mask `client_secret`, access tokens, and refresh tokens; no view or log SHALL echo them in plaintext. Masking SHALL be applied in a single serialization layer.

#### Scenario: Secret and tokens masked in directory and matrix (场景 114)
- **WHEN** an admin or viewer browses a connector configuration (which references a `client_secret`) and a user's authorization state (which holds a refresh token)
- **THEN** `client_secret`, access tokens, and refresh tokens are all masked in every view, and no audit log entry echoes them in plaintext

