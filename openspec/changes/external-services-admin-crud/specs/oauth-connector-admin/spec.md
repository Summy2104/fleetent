# oauth-connector-admin Specification

## MODIFIED Requirements

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
