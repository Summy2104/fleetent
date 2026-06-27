# agent-config-single-source

## ADDED Requirements

### Requirement: agents 表是 agent 配置的单一当前态真相源

agent 的全部配置 SHALL 以**当前态**形式存于 `agents` 表的列上,无版本化、无 `active_version_id` 间接层。运行时字段(`system_prompt`、`allowed_tools`、`model_overrides`、`memory_namespace`、`skills_dir`)与 caps 字段(`features`、`plugins`、`allowed_skills`、`config_overrides`、`supports_dm`、`supports_groups`、`icon`)统一住在 `agents` 行内。配置的所有读取方(materialize、credential 槽解析、控制台投影)MUST 直接读 `agents`,不得经任何版本指针解析。

#### Scenario: 编辑配置就地更新 agents 行

- **WHEN** 平台控制台修改某 agent 的 system_prompt / allowed_tools / model_overrides / memory_namespace / skills_dir 或 caps 字段
- **THEN** 系统就地 UPDATE 该 agent 的 `agents` 行,不创建任何新版本、不改任何版本指针

#### Scenario: materialize 从 agents 读全部配置字段

- **WHEN** 平台为某 agent 物化 agent.yaml(直接物化或 node desired-state)
- **THEN** 运行时字段与 caps 字段全部取自该 agent 的 `agents` 行,且物化产物与改动前语义一致

### Requirement: agent 配置写入收口到单一更新路径

所有"修改 agent 配置"的写入 SHALL 经由单一的配置更新函数(choke point)落库,而非分散在多个 store 入口。该函数 MUST 是配置变更的唯一就地写入点,以便未来可在此挂接可选的历史/快照逻辑而不改动调用方。

#### Scenario: 控制台配置编辑经统一更新路径

- **WHEN** 任一控制台编辑端点修改 agent 配置(prompt/tools/model/memory/skills_dir/caps/config_overrides)
- **THEN** 写入经由统一的配置更新函数完成,落 `agents` 表当前态

#### Scenario: 未来历史扩展为纯加法

- **WHEN** 未来需要为配置编辑增加 append-only 快照/回滚
- **THEN** 仅需在统一更新函数内增加"写前存快照"一步,无需改动任何现有调用方或读取路径

### Requirement: agent 配置中的模型凭证只引用 env 变量名,绝不内联明文 secret

agent 配置(含 `model_overrides` 内的模型目标)SHALL 只以 `api_key_env`(环境变量名)引用模型凭证;明文 secret MUST NOT 写入 `agents` 表的配置列、也 MUST NOT 出现在物化后的 agent.yaml。明文凭证经独立的 per-agent secret 注入路径(`/admin/agents/{name}/secrets` + node 注入)下发。本保证从已退役的 apply 契约迁移而来,在配置改由 `agents` 单一真相源承载后依然成立(数据主权)。

#### Scenario: 模型配置物化只含 env 名

- **WHEN** 平台为某 agent 物化 agent.yaml(直接物化或 node desired-state)
- **THEN** model 目标只携带 `api_key_env` 变量名,物化产物中不含任何明文 API key

#### Scenario: 明文 secret 不入配置列

- **WHEN** 控制台为 agent 设置模型凭证
- **THEN** 明文值落 per-agent secret store(经注入路径下发),`agents` 表配置列只保存对 env 变量名的引用
