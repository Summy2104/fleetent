## Why

fleetent 正在从 MVP 阶段的平铺代码结构，进入多人 / 多 Codex 窗口并行开发阶段。当前
capability 文档已经描述了产品能力边界，但代码层还没有明确 package 归属、public API、import
方向、表归属、配置命名空间和渐进迁移规则。

本 change 先建立模块化单体的组织契约，避免后续 intelligence、observability、deployment 等模块并行
开发时各自定义边界、制造冲突。目标仍然是单进程、单仓库、on-premises 友好的模块化单体，而不是立即
改成微服务或完整 DDD 分层。

## What Changes

- 新增 `module-boundaries` 能力，定义项目级模块化单体规则。
- 定义 capability group 到 Python package 的规范映射，包括 runtime、governance、platform、
  channels、intelligence、integrations、observability、infrastructure。
- 定义 public API 与 internal implementation 的约定，避免跨模块 import 私有实现。
- 定义数据库表、配置命名空间、migration 和对外 DTO 的归属规则。
- 定义依赖方向和禁止的跨模块访问方式。
- 定义从平铺文件到模块目录的渐进迁移策略：
  - 新代码进入目标 package；
  - 旧平铺模块在被大幅触碰时迁移；
  - 迁移期间允许保留 re-export 兼容 shim；
  - 本 change 不做大规模机械搬迁。
- 明确与进行中的 `introduce-database-runtime-boundary` change 的关系：
  - 本 change 依赖 DB runtime 的 store 访问契约；
  - 本 change 不重新定义 `fleetent.db`、`database_url` 或具体 adapter 行为。

## Capabilities

### New Capabilities

- `module-boundaries`：项目级模块边界、代码组织、public API、internal import、表归属、配置归属、
  渐进迁移策略。

### Modified Capabilities

- `db-migration`：补充 migration 的模块归属规则；具体 database runtime 边界仍由
  `introduce-database-runtime-boundary` 定义。

## Impact

- **代码组织**：
  - 定义 `src/fleetent/` 下的目标 package 结构，但不要求立即移动现有文件。
  - 后续新模块优先按目标 package 写入。
  - 旧平铺模块迁移时可保留兼容 re-export shim。
- **API**：
  - 跨模块调用应通过模块导出的 public function、dataclass 或 service interface。
  - 禁止跨模块 import 另一模块的 internal implementation。
- **数据**：
  - 每张持久化表有且只有一个 owner module。
  - 模块不得直接读写其他模块 owned table，只能通过 owner 的 public API。
- **配置**：
  - 每个模块拥有稳定配置命名空间，例如 `memory.*`、`knowledge_base.*`、`observability.*`、
    `vector_store.*`。
- **依赖**：
  - 不引入新的运行时依赖。
  - 不引入 ORM、AI framework 或云托管专有服务。
- **并行开发**：
  - 为多个 Codex 窗口 + worktree 并行开发提供共同边界，避免不同窗口各自发明不兼容接口。
