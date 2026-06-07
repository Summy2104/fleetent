## MODIFIED Requirements

### Requirement: Inline credential entry at the referencing field

凭据值 SHALL 在引用该密钥的字段就地输入（Provider「API Key」、KB connector 的 token 字段），而非在独立的「所需密钥」面板。每个此类字段 SHALL 呈现一个统一控件，默认态为**输入值**，并提供**引用现有变量**为可选高级态。控件 SHALL NOT 回显任何已存的密钥值。

此前要求「per-slot 在面板里选 mode + inject 才出现输入框」被本要求取代：输入入口从面板上移到字段。

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

此前要求「面板内 per-slot 选 operator/inject 并就地 inject 输值」被本要求取代。

#### Scenario: 面板只读列出与状态
- **WHEN** 打开一个有 `*_env` 引用的 agent 的所需密钥面板
- **THEN** 每个槽显示 env 名、来源、set/unset 状态
- **AND** 面板内不提供值输入或 mode 单选控件

#### Scenario: 面板校验部署缺失
- **WHEN** 某 operator 槽在主机 .env 未填 / 某 inject 槽未保存
- **THEN** 面板把它标为 unset 并可一键列出缺失项
