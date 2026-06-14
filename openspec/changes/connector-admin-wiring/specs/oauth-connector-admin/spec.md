# oauth-connector-admin Specification

## MODIFIED Requirements

### Requirement: Per-user authorization matrix

The admin face SHALL present a `(user, service)` authorization matrix whose per-cell state comes from `external_credentials.status`: not-authorized（无凭证）、authorized（有效凭证，含 granted scopes）、needs-reauthorization（`needs_reauth`，refresh 失效）、credential-error（`error`，可重试）。矩阵为**单层全局**，SHALL NOT 再按 owning-agent 范围划分（承接 P0 移除的覆盖层）。矩阵可按 user 或按 service 视角聚合。状态判定 SHALL 取自 Vault（`external_credentials`），SHALL NOT 在此重算。

#### Scenario: Mixed authorization states shown
- **WHEN** an admin filters the matrix to a user who has authorized `google-drive`, never authorized `github`, and whose `notion` refresh token has expired
- **THEN** `google-drive` shows authorized with its scopes, `github` shows not-authorized, and `notion` shows "needs reauthorization"

#### Scenario: Credential error distinguished from needs-consent
- **WHEN** Vault 对某 `(user, service)` 返回 `status=error`
- **THEN** 该格显示 "credential error (retryable)"，区别于 not-authorized 与 needs-reauthorization

#### Scenario: Switch matrix viewpoint
- **WHEN** an admin toggles between the by-user and by-service views
- **THEN** the same authorization data is re-aggregated under the selected axis

### Requirement: Admin cannot complete first-time consent on behalf of a user

The admin face SHALL NOT provide any path to complete a user's first-time OAuth consent or to fill in a user's API key. 首次授权 SHALL 由用户本人完成（OAuth 浏览器跳转 / 用户自助提交 key）。No delegate-consent endpoint SHALL exist.

#### Scenario: No delegate-consent entry for unauthorized cell
- **WHEN** an admin opens an unauthorized `(user, service)` cell
- **THEN** the UI offers no "authorize on behalf of" action and states that first-time authorization must be completed by the user; no delegate endpoint accepts the request

### Requirement: Admin revoke on behalf of a user

An admin SHALL be able to revoke a `(user, service)` grant. The revoke semantics（删除本地凭证、尽力调用外部 revoke endpoint）are delegated to the Vault（见 `oauth-token-lifecycle`）。This face only triggers it, requires confirmation, and audits it. After revoke the user returns to `NeedsConsent` on next use.

#### Scenario: Revoke with confirmation and audit
- **WHEN** an admin revokes `(Alice, google-drive)` and confirms the high-risk action
- **THEN** the Vault deletes the credential and calls the external revoke endpoint, Alice must re-authorize on next use, and the revoke is written to the audit log

#### Scenario: Revoke requires admin
- **WHEN** a viewer attempts to revoke a `(user, service)` grant
- **THEN** the request is rejected with 403

### Requirement: Offboarding linkage visibility

The admin face SHALL display the result of the Vault auto-revoking all of a user's external credentials when the user is disabled, including which services were revoked and whether each succeeded, for offboarding audit.

#### Scenario: Show offboarding revoke result
- **WHEN** a user has been disabled and the admin opens that user's external-services view
- **THEN** the face shows each service whose credential was auto-revoked by the linkage and the success/failure of each external revoke

### Requirement: Credential lifecycle observability

The admin face SHALL show, per service, access-token auto-refresh success/failure rate and the count of re-authorizations caused by refresh-token expiry, sourced from Vault token-lifecycle data（见 `oauth-token-lifecycle`）。

#### Scenario: Per-service refresh metrics
- **WHEN** an admin opens the lifecycle view for a service
- **THEN** it shows the auto-refresh success/failure rate and the re-authorization count for that service
