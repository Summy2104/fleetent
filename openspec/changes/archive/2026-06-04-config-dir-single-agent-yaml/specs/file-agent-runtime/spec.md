## MODIFIED Requirements

### Requirement: Single-file agent home loading
当 agent config 目录存在 `agent.yaml`（`FLEETENT_HOME/config/agent.yaml`）时，运行时 SHALL 将其作为唯一且默认的 agent 加载，优先于 `config/agents/` 多扫描；该单文件不要求位于 `<name>/` 子目录，因此 SHALL 跳过「目录名等于 name」校验。

#### Scenario: Config-dir agent.yaml is loaded as the sole agent
- **WHEN** `FLEETENT_HOME/config/agent.yaml` 存在且校验通过
- **THEN** 索引只含该一个 agent（`name` 取自文件）
- **AND** 不扫描 `config/agents/`

#### Scenario: Config-dir single agent is forced default
- **WHEN** 以单文件模式加载 `config/agent.yaml`，且其 `bindings.default` 为 false 或缺省
- **THEN** 索引的 `default` 等于该 agent 的 `name`
- **AND** 未匹配具体 channel/user 的请求路由到该默认 agent

#### Scenario: Config-dir file skips directory-name check
- **WHEN** `config/agent.yaml` 的 `name` 与任何目录名无关（无 `<name>/` 父目录）
- **THEN** 加载成功，不因目录名不匹配而失败
- **AND** 仍执行 inline secret 拒绝校验

#### Scenario: Falls back to multi-scan when config-dir file absent
- **WHEN** `FLEETENT_HOME/config/agent.yaml` 不存在
- **THEN** 运行时回退到既有 `config/agents/` 多扫描
- **AND** 多扫描的 default 仍由 `bindings.default` 决定

#### Scenario: Config-dir bindings still populate routing
- **WHEN** 单文件 agent 声明 `bindings.channels` 或 `users`
- **THEN** 这些绑定进入 `by_channel`/`by_user` 路由表
- **AND** 同时该 agent 仍是 default
