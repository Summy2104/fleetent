## ADDED Requirements

### Requirement: Knowledge base 作为顶层独立组件四分

`knowledge_base` SHALL 作为顶层独立组件存在（`src/fleetent/knowledge_base/`），与 runtime/session/governance 并列，而非置于 `intelligence/` 业务树下。它 SHALL 按职责四分为 `core` / `retrieval` / `ingest` / `management` 子包：`core` 提供读写共享的持久化底层；`retrieval` 提供 agent 对话期的只读检索；`ingest` 提供外部数据摄取与 KB 内容写入；`management` 提供 KB 容器与 agent 绑定管理。

#### Scenario: 四块按职责隔离
- **WHEN** 检查 `knowledge_base` 包结构
- **THEN** SHALL 存在 `core` / `retrieval` / `ingest` / `management` 四个子包
- **AND** 检索逻辑 SHALL 在 `retrieval`、摄取/内容写 SHALL 在 `ingest`、容器与绑定写 SHALL 在 `management`、持久化底层 SHALL 在 `core`

### Requirement: Core 暴露 Readable / Writable 读写接口

`knowledge_base.core` SHALL 暴露 `KnowledgeReadable` 与 `KnowledgeWritable` 两个 Protocol，并由单一实现（`KnowledgeStore`）同时满足两者。读边界（retrieval）SHALL 在类型上只依赖 `KnowledgeReadable`，写边界（ingest/management）SHALL 依赖 `KnowledgeWritable`。

#### Scenario: retrieval 类型上只见读接口
- **WHEN** 检查 `retrieval` 函数对 core store 的依赖
- **THEN** 其签名 SHALL 只接受/返回 `KnowledgeReadable`
- **AND** 在类型层面 SHALL NOT 可达写方法（upsert/delete/archive）

#### Scenario: 单一实现满足两个 Protocol
- **WHEN** 检查 core store 实现
- **THEN** SHALL 只有一份 `KnowledgeStore` 实现
- **AND** 它 SHALL 同时满足 `KnowledgeReadable` 与 `KnowledgeWritable`

### Requirement: KB 内容写入路径单一（派生视图）

KB 是数据源的**派生视图**。KB 内容（文档/chunk/图谱）的写入 SHALL 只经 `ingest`（摄取/同步）一条路径。`retrieval` SHALL NOT 暴露任何 KB 内容写接口。agent / reflection 对知识的贡献 SHALL NOT 直接写 KB，而 SHALL 写其真相源（agent-curated 沉淀源），再经 connector sync 流入 KB，以保证 KB 始终是数据源的纯派生、可追溯、可重新摄取。

#### Scenario: retrieval 无写接口
- **WHEN** 检查 `retrieval` 子包的公共面
- **THEN** SHALL NOT 暴露 KB 内容的写/删除/归档接口

#### Scenario: 内容写入唯一经 ingest
- **WHEN** 写入或删除 KB 文档/chunk/图谱
- **THEN** SHALL 经 `ingest` 子包完成
- **AND** 不存在绕过 ingest 的 KB 内容写入路径

### Requirement: Ingest 经注入 settings 消解 connector 双源

`knowledge_base.ingest` 的对外入口 SHALL 接收注入的 `KnowledgeBaseSettings`（经 `as_knowledge_base_settings` adapter），SHALL NOT 自读 agent 侧家目录配置来发现 connector。connector 配置来源由调用方（platform 控制面或单机 ingest CLI）注入。

#### Scenario: ingest 不自读 agent config
- **WHEN** 检查 ingest 摄取入口
- **THEN** 它 SHALL 接收注入的 settings 参数
- **AND** SHALL NOT 通过家目录 `_kb_config` 自行发现 connector 配置

### Requirement: KB 依赖方向护栏

系统 SHALL 以 CI 强制的测试护栏断言 KB 的依赖方向：`knowledge_base.retrieval` MUST NOT import `knowledge_base.ingest`；`knowledge_base.core` MUST NOT import `retrieval`/`ingest`/`management`；`knowledge_base`（含全部子包）MUST NOT import `fleetent.platform.*`。

#### Scenario: 读边界不依赖写边界
- **WHEN** 护栏测试检查 `knowledge_base.retrieval` 的 import
- **THEN** 若其中出现对 `knowledge_base.ingest` 的 import，测试 SHALL 失败

#### Scenario: 组件不依赖控制面
- **WHEN** 护栏测试检查 `knowledge_base` 任一子包的 import
- **THEN** 若其中出现对 `fleetent.platform.*` 的 import，测试 SHALL 失败

### Requirement: 公共 API 与旧路径过渡兼容

迁移为四块组件 SHALL NOT 改变 KB 检索/摄取/管理的公共 API 行为与语义。旧 import 路径 `fleetent.intelligence.knowledge_base` SHALL 通过 re-export shim 在迁移过渡期保持可用。

#### Scenario: 行为不变
- **WHEN** 调用方经新路径使用任一 KB 公共 API
- **THEN** 其行为 SHALL 与迁移前完全一致

#### Scenario: 旧路径过渡期可用
- **WHEN** 既有代码经旧路径 `fleetent.intelligence.knowledge_base` import
- **THEN** 在迁移过渡期 SHALL 仍然可用（re-export shim）
