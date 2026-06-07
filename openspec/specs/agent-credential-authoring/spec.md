# agent-credential-authoring Specification

## Purpose
Friendly per-agent credential authoring in the admin console: each `*_env` reference in an
agent's materialized definition is a credential slot whose value is either filled by the
operator on the deploy host or injected by the platform (encrypted at rest). Secret values
are entered inline on the field that references them (Provider API Key, KB connector tokens),
value-first: typing a value encrypts it and auto-derives the env name; an advanced toggle
references an existing env var instead. Cross-agent entities (providers/connectors) use a
shared secret scope. The required-secrets panel is a read-only deploy-readiness overview. The
platform derives required env names, stores inject-mode values encrypted, and never echoes a
value back. Created by archiving changes agent-credential-authoring and credential-inline-field.

## Requirements
### Requirement: Per-agent credential slots

每个 `agent.yaml` 中需要 `*_env` 引用的位置（model target、MCP server、Slack connector、KB
connector）SHALL 在平台侧对应一条凭据槽元数据 `{ env_name, mode }`。`mode` SHALL 为
`operator`（默认）或 `inject`。槽元数据 SHALL NOT 出现在生成的 `agent.yaml` 中——`agent.yaml`
只含 `*_env` 引用本身。

#### Scenario: 未输值的槽为 operator 模式
- **WHEN** 一个密钥槽被引用但未就地输入值（也未引用平台已存值）
- **THEN** 该槽 mode 为 `operator`
- **AND** 平台不为该槽存储任何密钥值（值由运维在主机 .env 填）

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

### Requirement: Inline credential entry at the referencing field

凭据值 SHALL 在引用该密钥的字段就地输入（Provider「API Key」、KB connector 的 token 字段），而非在独立的「所需密钥」面板。每个此类字段 SHALL 呈现一个统一控件，默认态为**输入值**，并提供**引用现有变量**为可选高级态。控件 SHALL NOT 回显任何已存的密钥值。

#### Scenario: 默认就地输值
- **WHEN** 运维在 Provider 或 KB connector 的密钥字段查看控件且未切换模式
- **THEN** 控件默认呈现一个写后不回显的值输入
- **AND** 不要求运维先填 env 变量名

#### Scenario: 输值即加密保存并自动派生引用
- **WHEN** 运维在值输入里保存一个密钥值
- **THEN** 该值经加密 secret store 保存（inject 语义）
- **AND** 平台自动派生稳定的 env 名并把该字段的 `*_env` 引用指向它
- **AND** 运维无需手填 env 名

#### Scenario: 高级引用模式不存值
- **WHEN** 运维展开「引用现有变量」并填入一个 env 名
- **THEN** 该槽切为 operator 模式且只记 env 名
- **AND** 平台不为该槽存储任何密钥值（值由运维在主机 .env 填）

#### Scenario: 已存值不回显
- **WHEN** 编辑一个已保存 inject 值的字段
- **THEN** 控件只显示 set 状态，不回显原值
- **AND** 替换值需显式重新输入

### Requirement: Auto-derived env name on inline entry

当运维就地输值而未自定义 env 名时，平台 SHALL 按来源实体稳定派生 env 名（Provider key → `FLEETENT_MODEL_<PROVIDER_ID>_API_KEY`；KB connector token → `FLEETENT_KB_<CONNECTOR_ID>_<SLOT>`，均大写且 `-`→`_`），并将其写入该实体配置对应的 `*_env` 字段。派生或设定撞名时 SHALL fail loud。

#### Scenario: provider 输值派生模型 key 名
- **WHEN** provider `fast-claude` 就地保存一个 API key 值
- **THEN** 派生 env 名 `FLEETENT_MODEL_FAST_CLAUDE_API_KEY`
- **AND** provider 配置的 `api_key_env` 被设为该名

#### Scenario: 派生名撞名被拒
- **WHEN** 两个字段派生或被设为同一 env 名
- **THEN** authoring fail loud，提示修改 env 名

### Requirement: Shared credential scope for cross-agent entities

Provider 与 connector 是跨 agent 共享的实体。平台 SHALL 支持一个非 agent 维度的 shared 密钥作用域来承载其 inline 值，使一个 provider/connector 的密钥可被多个 agent 复用。materialize resolver 解析某 `*_env` 时 SHALL 优先 per-agent 槽、回退 shared 槽。`agent.yaml` SHALL 仍只含 `*_env` 引用，inline 值只进加密 store。

#### Scenario: shared 值被多 agent 复用
- **WHEN** 一个 provider 的 key 以 shared 作用域保存
- **AND** 两个 agent 都引用该 provider
- **THEN** materialize 两个 agent 时都能解出该 shared 值
- **AND** 无需为每个 agent 重复输入

#### Scenario: per-agent 槽优先于 shared
- **WHEN** 同一 env 名同时存在 per-agent 槽与 shared 槽
- **THEN** materialize 该 agent 时取 per-agent 槽的值

### Requirement: Required-secrets panel as read-only deploy overview

「所需密钥」面板 SHALL 是只读的部署就绪总览，列出当前配置引用的每个 `*_env` 的 `{ env_name, source, status }` 与缺失校验、`.env` 模板复制。该面板 SHALL NOT 作为密钥值的输入入口（输入入口在引用字段的 CredentialField）。

#### Scenario: 面板只读列出与状态
- **WHEN** 打开一个有 `*_env` 引用的 agent 的所需密钥面板
- **THEN** 每个槽显示 env 名、来源、set/unset 状态
- **AND** 面板内不提供值输入或 mode 单选控件

#### Scenario: 面板校验部署缺失
- **WHEN** 某 operator 槽在主机 .env 未填 / 某 inject 槽未保存
- **THEN** 面板把它标为 unset 并可一键列出缺失项
