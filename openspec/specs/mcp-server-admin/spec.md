# mcp-server-admin Specification

## Purpose
TBD - created by archiving change 2026-06-02-connector-management. Update Purpose after archive.
## Requirements
### Requirement: MCP server list and connection status
The admin face SHALL list all configured MCP servers (stdio / HTTP transport) with a
connection status aligned to the `mcp` domain: connected, startup-degraded (masked at
startup), probe-failing-reconnecting (exponential backoff), and marked-permanently-
unavailable. Each entry SHALL show its owning agent (or "global default" for entries
authored without an agent scope), registered tool count, the `server__{tool}`
namespace list, and the last handshake/probe time. The list SHALL support filtering by
owning agent. Connection state is delegated to the `mcp` domain and SHALL NOT be
recomputed here.

#### Scenario: Startup-degraded server visible (场景 112)
- **WHEN** an admin opens the MCP server list while an HTTP MCP server was degraded after a failed startup handshake
- **THEN** that server shows "startup-degraded" with registered tool count 0, the rest of the platform is unaffected, and a "manual reconnect" action is available

#### Scenario: Connection states distinguished
- **WHEN** servers are respectively connected, reconnecting under backoff, and marked permanently unavailable
- **THEN** the list shows each distinct status as reported by the `mcp` domain

#### Scenario: Owning agent shown and filterable
- **WHEN** an admin filters the MCP server list by agent `billing`
- **THEN** only `billing`-owned servers and applicable global defaults are listed, each labeled with its owning agent or "global default"

### Requirement: Registered tool namespace visibility
The admin face SHALL let an admin expand an MCP server to view its registered tools (name, description, input-schema summary). Tool names SHALL be shown under the `{server_id}__{tool_name}` (double-underscore) namespace so an admin can reference `server__*` tools when configuring an Agent's `allowed_tools`. Access control of the allowlist itself belongs to the `governance` domain; this face only makes tools visible.

#### Scenario: Tool namespace shown (场景 113)
- **WHEN** an admin expands a connected MCP server `github` that has registered tools
- **THEN** its tools are listed under the `github__{tool}` namespace for reference when configuring Agent `allowed_tools`

#### Scenario: Tool schema summary visible
- **WHEN** an admin expands a server's tool entry
- **THEN** the tool's name, description, and input-schema summary are shown

### Requirement: Manual reconnect and re-handshake
The admin face SHALL provide a "manual reconnect / re-handshake" action that triggers the `mcp` domain to re-attempt the handshake, and SHALL audit it. Connection failure / degradation SHALL NOT block platform startup; this face only presents status and triggers the action.

#### Scenario: Manual reconnect triggers handshake and audit
- **WHEN** an admin clicks "manual reconnect" on a degraded MCP server
- **THEN** the `mcp` domain re-attempts the handshake and the action is written to the audit log

#### Scenario: Reconnect requires admin
- **WHEN** a viewer attempts to trigger a manual reconnect or change an MCP server configuration
- **THEN** the request is rejected with 403

### Requirement: MCP doctor diagnostic entry
The admin face SHALL provide an entry to trigger the `mcp doctor` diagnostic and render its conclusions as a red/yellow/green checklist. Sensitive authentication values (tokens, API keys, credentials embedded in URLs) SHALL be masked.

#### Scenario: Doctor checklist masked
- **WHEN** an admin or viewer triggers the `mcp doctor` diagnostic
- **THEN** the result is rendered as a red/yellow/green checklist with all sensitive authentication values masked, never echoed in plaintext

### Requirement: MCP management permissions and audit
MCP server configuration changes and manual reconnects SHALL be admin-only; viewers MAY only browse the server list, connection status, and doctor conclusions. All write actions SHALL be written to the audit log (who, when, which server, what action).

#### Scenario: Viewer read-only on MCP face
- **WHEN** a viewer opens the MCP server list and doctor results
- **THEN** they can browse status and diagnostics but every write action (config change, manual reconnect) returns 403

#### Scenario: Unauthenticated rejected
- **WHEN** a request to any `/admin/mcp/*` endpoint carries no valid login session
- **THEN** the response is 401

### Requirement: MCP servers managed natively in the React SPA

The React admin SPA SHALL render MCP servers natively (within the Connectors domain, not a deep-link to legacy) and SHALL support the full lifecycle against the existing admin API: list, create, edit, delete, test, reconnect, view tools, and run doctor. This closes the legacy create-only gap. **Create/edit 的鉴权部分 SHALL 按 `auth_type` 动态渲染**:选 `api_key` 显示单个 env-name 字段、选 `oauth_client_credentials` 显示 token_url / client_id / scope / client_secret-env-name 字段(字段集由 `mcp-auth-config` 的类型 schema 驱动)。表单 MUST NOT 暴露扁平 `api_key_env` 输入(改由结构化 `auth_config` 承载),且 MUST NOT 接受 secret 明文(只接受 env 引用名,值经 secret 接口存 `agent_secrets`)。**Create SHALL 允许选择 server scope** —— 全局默认(`agent_id` 为空)或某 owning agent(agent-private,经 create 请求传 `agent_id`),闭合"建窗只能建全局行"的实现缺口(owning agent 的展示/过滤见本 capability 既有要求)。

#### Scenario: Edit, delete, and test an MCP server from the SPA

- **WHEN** an admin edits an existing MCP server and saves, deletes one (with confirmation), or tests one from the React admin SPA
- **THEN** the SPA calls `PUT /admin/mcp/servers/{id}` / `DELETE /admin/mcp/servers/{id}` / `POST /admin/mcp/servers/{id}/test` and reflects the result

#### Scenario: View tools and reconnect in the SPA

- **WHEN** an admin lists an MCP server's tools or reconnects it from the React admin SPA
- **THEN** the SPA calls `GET /admin/mcp/servers/{id}/tools` and `POST /admin/mcp/servers/{id}/reconnect`, and shows the outcome

#### Scenario: 鉴权表单按 auth_type 动态渲染

- **WHEN** 管理员在 create/edit 表单切换 `auth_type`(api_key ↔ oauth_client_credentials)
- **THEN** 表单显示该类型对应的字段集(api_key:1 个 env 名;oauth:token_url/client_id/scope/client_secret-env),且只收 env 引用名、不收 secret 明文、不显示扁平 `api_key_env` 输入

#### Scenario: 建全局或 agent 私有 server

- **WHEN** 管理员在 create 选择 scope=全局(不选 agent)或 scope=某 agent
- **THEN** SPA 在 create 请求带 `agent_id`(全局为空 / 私有为该 agent id),注册表据此建全局默认行或 agent 私有行

