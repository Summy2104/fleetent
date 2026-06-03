## MODIFIED Requirements

### Requirement: Connector directory and configuration
An admin SHALL be able to list all declared OAuth connectors and create or edit a
connector configuration without changing core code. Each entry SHALL show `id`, the
owning agent (or "global default" when unowned), authorize/token endpoints, scopes,
`client_id`, enabled flag, authorized-user count, and last authorize/refresh time. The
directory SHALL support filtering by owning agent. The same connector `id` MAY exist once
per agent plus once as a global default. Sensitive values (`client_secret`) SHALL never
be returned in plaintext.

#### Scenario: List connectors with masked secret
- **WHEN** an admin or viewer opens the connector directory
- **THEN** each connector shows id, owning agent, authorize/token endpoints, scopes, and `client_id`, while `client_secret` is masked and never returned in plaintext

#### Scenario: Add a connector takes effect
- **WHEN** an admin creates a new OAuth connector configuration and saves
- **THEN** the connector appears in the directory and becomes available without a core code change or service restart

#### Scenario: Viewer cannot edit configuration
- **WHEN** a viewer attempts to create or edit a connector configuration
- **THEN** the request is rejected with 403 and the directory remains read-only for viewers

#### Scenario: Filter directory by agent
- **WHEN** an admin filters the directory by agent `billing`
- **THEN** only `billing`-owned connectors and applicable global defaults are listed, each labeled with its owning agent or "global default"

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
