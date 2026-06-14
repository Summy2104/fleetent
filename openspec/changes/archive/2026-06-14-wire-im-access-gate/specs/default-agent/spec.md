# default-agent Delta

## MODIFIED Requirements

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
