# default-agent Specification

## Purpose
TBD - created by archiving change im-user-access-control. Update Purpose after archive.
## Requirements
### Requirement: Global default agent configuration
The system SHALL determine the default agent from the file-based agent index: the single agent whose file sets `bindings.default: true`. When an incoming message is not already attributed to a specific agent by its connector connection, that default agent (if present) is used. Resolving the default SHALL NOT read the database. （旧的"无 channel/user 绑定时用 default"措辞已退役——channel/user 文件绑定路由已随 IM 访问模型移除；agent 由连接器连接识别，default 是兜底。）

#### Scenario: Default agent declared in a file
- **WHEN** exactly one agent file sets `bindings.default: true` and the incoming message's connector does not identify a specific agent
- **THEN** that agent is applied to the request, resolved from its file with no DB read

#### Scenario: No default agent declared
- **WHEN** no agent file sets `bindings.default: true`
- **THEN** default resolution returns nothing and the request proceeds with no agent (bare run)

### Requirement: Agent lookup priority order
The system SHALL resolve the agent for each incoming message in the following priority order, served entirely from the file-based agent index: **connector-identified agent > default agent > bare run**. The connector connection that received the message identifies the agent (one-agent-one-bot); the prior channel-binding and user-binding lookup layers are removed (that file-bindings routing model has been retired with the IM access model).

#### Scenario: Connector identifies the agent
- **WHEN** a message arrives on a connector connection bound to agent X
- **THEN** agent X is used (no channel/user binding lookup occurs)

#### Scenario: Connector does not identify an agent — default wins
- **WHEN** the incoming message is not attributed to a specific agent and a default agent file exists
- **THEN** the default agent is used

#### Scenario: No identified agent and no default — bare run
- **WHEN** no agent is identified by the connector and none declares a default
- **THEN** the request proceeds with no agent (bare run)

### Requirement: Admin can set default agent via CLI

The platform SHALL expose `PUT /admin/agents/{name}/default` (set the named agent as default) and `DELETE /admin/agents/default` (clear the current default). The default SHALL be a control-plane attribute persisted in the management DB (a single default agent per tenant), NOT edited directly on node-side `agent.yaml` files. Setting a new default SHALL clear any previously-default agent in the same tenant. The materialize path SHALL emit `bindings.default: true` into the agent.yaml content for the agent marked default, so node-side scan continues to resolve the default from `bindings.default` unchanged. Both endpoints MUST require admin role and write an audit entry.

The legacy CLI `set-default-agent` (which directly edited `agent.yaml` files) is superseded by these endpoints; it is removed by the `slim-admin-cli` change.

#### Scenario: Set default agent via HTTP

- **WHEN** admin calls `PUT /admin/agents/basic/default`
- **THEN** agent `basic` is marked default in the management DB, any previously-default agent in the tenant is cleared, and an audit entry is written

#### Scenario: Default propagates through materialize

- **WHEN** agent `basic` is marked default and the node pulls its materialized agent.yaml
- **THEN** the materialized content has `bindings.default: true` for `basic`, and node-side scan resolves `basic` as the default with no DB read

#### Scenario: Clear default agent via HTTP

- **WHEN** admin calls `DELETE /admin/agents/default`
- **THEN** no agent is marked default; materialize emits no `bindings.default: true`, and default resolution returns nothing

#### Scenario: Existing file-based default is backfilled

- **WHEN** the change is deployed on an install where an agent.yaml already has `bindings.default: true`
- **THEN** that agent's default flag is backfilled into the control-plane attribute, and the materialized output preserves `bindings.default: true` for the same agent (no behavior change before/after migration)

#### Scenario: Non-admin cannot set default

- **WHEN** a non-admin user calls `PUT /admin/agents/{name}/default` or `DELETE /admin/agents/default`
- **THEN** the system returns 403

