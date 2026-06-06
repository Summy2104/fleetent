## ADDED Requirements

### Requirement: Per-agent credential slots

The platform SHALL maintain per-agent credential slot metadata for every generated
`*_env` reference.

每个 `agent.yaml` 中需要 `*_env` 引用的位置（model target、MCP server、Slack connector、KB
connector）SHALL 在平台侧对应一条凭据槽元数据 `{ env_name, mode }`。`mode` SHALL 为
`operator`（默认）或 `inject`。槽元数据 SHALL NOT 出现在生成的 `agent.yaml` 中——`agent.yaml`
只含 `*_env` 引用本身。

#### Scenario: 槽默认 operator 模式
- **WHEN** 一个新的密钥槽被创建且未显式设 mode
- **THEN** 该槽 mode 为 `operator`
- **AND** 平台不为该槽存储任何密钥值

#### Scenario: env 变量名自动派生
- **WHEN** 一个密钥槽被创建且运维未自定义 env 名
- **THEN** 平台派生稳定的 `FLEETENT_AGENT_<NAME>_<SLOT>` 形式的 env 名

#### Scenario: env 变量名不随改名静默漂移
- **WHEN** agent 改名后未触发显式重算
- **THEN** 已有槽的 env_name 保持不变

#### Scenario: env 名撞名被拒
- **WHEN** 两个槽派生或被设为同一个 env 名
- **THEN** authoring fail loud，提示修改 env 名

#### Scenario: 槽元数据不进 agent.yaml
- **WHEN** 平台 materialize 一个含 inject 槽的 agent
- **THEN** 生成的 `agent.yaml` 仅含 `*_env` 引用
- **AND** 不含 `mode` 或任何密钥值

### Requirement: Encrypted secret store

平台 SHALL 提供加密 secret store，仅用于 `inject` 模式的密钥值。值 SHALL 以对称 AEAD 加密后
存储；主密钥 SHALL 来自进程环境变量 `FLEETENT_SECRET_KEY`。store SHALL NOT 以明文持久化任何
密钥值，且 SHALL NOT 依赖任何外部托管密钥服务。

#### Scenario: inject 值加密落库
- **WHEN** 一个 inject 槽被写入明文值
- **THEN** 持久化的是密文，明文不出现在数据库中

#### Scenario: 缺主密钥时 inject 操作 fail loud
- **WHEN** `FLEETENT_SECRET_KEY` 未设置或无效
- **AND** 发生 inject 值的写入或读取
- **THEN** 操作 fail loud
- **AND** operator 模式的槽不受影响

#### Scenario: status 不泄露明文
- **WHEN** 查询某槽的状态
- **THEN** 只返回 `set` 或 `unset`
- **AND** 不返回密钥值

### Requirement: Write-only credential API

平台 SHALL 暴露 write-only 凭据 API。写入端点 SHALL 接收明文但 SHALL NOT 在任何响应中回显密钥
值。读取端点 SHALL 只暴露每个槽的 `{ env_name, mode, status }`。

#### Scenario: 写值不回显
- **WHEN** 通过 `PUT` 写入一个 inject 槽的值
- **THEN** 响应只含 `env_name` 和 `status: set`
- **AND** 响应不含写入的值

#### Scenario: 列槽不含明文
- **WHEN** `GET` 某 agent 的凭据列表
- **THEN** 每项含 `env_name` / `mode` / `status`
- **AND** 不含任何密钥值

#### Scenario: 空值写入被拒
- **WHEN** `PUT` 写入空值
- **THEN** 请求被拒绝
- **AND** 提示使用删除端点清除

### Requirement: Required-env derivation

平台 SHALL 提供端点，从某 agent 的当前定义派生其部署所需的 `*_env` 引用清单。每项 SHALL 含
env 名、来源标签（如 Models / MCP / Connectors / Knowledge）、mode 和 set/unset 状态。

#### Scenario: 派生反映当前配置
- **WHEN** 一个 agent 绑定了一个 MCP server 且引用了 model 与 Slack
- **THEN** required-env 列出对应的 model / MCP / Slack `*_env`

#### Scenario: 配置变更即时反映
- **WHEN** 该 agent 新增一个引用 `*_env` 的 MCP server
- **THEN** required-env 清单包含该新增 server 的 `*_env`

#### Scenario: 未 author 的字段不误报
- **WHEN** 某 agent.yaml 段（如 governance 旋钮）没有 `*_env` 引用
- **THEN** required-env 不为其产生条目
