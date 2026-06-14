# oauth-connector-admin Specification

## MODIFIED Requirements

### Requirement: Connector directory and configuration

An admin SHALL be able to list all declared external services and create / edit / delete a service configuration without changing core code. Each entry SHALL show `service_id`、`kind`、`protocol`（`oauth2_authcode` | `api_key`）、authorize/token endpoints、scopes、`client_id`、enabled flag. The directory SHALL be a single global registry —— 无 owning-agent 列、不支持按 agent 过滤（承接 P0 移除的 per-agent 覆盖层）。`client_secret` SHALL never be returned in plaintext。仅 admin 可写，viewer 只读。

#### Scenario: List services with masked secret and protocol
- **WHEN** an admin or viewer opens the external services directory
- **THEN** each entry shows `service_id`、`kind`、`protocol`、authorize/token endpoints、scopes、`client_id`，`client_secret` 被遮蔽且永不明文返回

#### Scenario: Add an OAuth service takes effect
- **WHEN** an admin creates a new `protocol="oauth2_authcode"` service and saves
- **THEN** 该服务出现在目录中，无需改核心代码或重启即可被授权使用

#### Scenario: Add an API-key service takes effect
- **WHEN** an admin creates a new `protocol="api_key"` service and saves
- **THEN** 该服务以 `protocol=api_key` 出现在目录中

#### Scenario: Viewer cannot edit configuration
- **WHEN** a viewer attempts to create / edit / delete a service configuration
- **THEN** the request is rejected with 403 and the directory remains read-only for viewers

#### Scenario: Delete a service
- **WHEN** an admin deletes a service and confirms
- **THEN** 该服务从目录移除，操作落审计
