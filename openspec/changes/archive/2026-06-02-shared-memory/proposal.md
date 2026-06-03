# shared-memory

## Why

当前 memory 能力只覆盖 User Memory。reflection 已经能识别“不适合写入个人记忆”的团队共识、项目惯例、
客户背景等内容，但只能产生 `suggest_shared_memory_or_kb` 建议，没有可落地的共享记忆实体。

Knowledge Base 适合保存企业文档和事实来源；Shared Memory 适合保存经过确认、短小、结构化、可直接用于
后续上下文选择的共享偏好、组织背景和操作惯例。本 change 建立 Shared Memory 的数据层和受控写入边界，
但不在第一版接入 prompt 注入策略。

## What Changes

- 新增独立 `SharedMemoryItem` 实体和 `shared_memory_items` 表。
- 支持 `scope_type`：`team`、`tenant`。
- 支持 memory type：`context`、`preference`、`procedure`。
- 支持状态：`active`、`stale`、`archived`。
- 提供 public API：创建、更新、归档、搜索、枚举可重建索引记录。
- 使用 vector namespace `shared:{scope_type}:{scope_id}` 写入和检索。
- 支持 reflection proposal apply 后写入 Shared Memory。
- 提供 admin/API 维护入口和 deterministic evaluation。

## Out Of Scope

- 不把 Shared Memory 混入 User Memory 表。
- 不接入 long-term context prompt 注入。
- 不定义 agent / tenant 默认启用策略、budget 分配或冲突优先级。
- 不做最终用户投票、复杂 ACL 或文档级证据图。
- 不把 Shared Memory 写入 Knowledge Base。

## Module Boundary Impact

- owning package：`fleetent.intelligence.memory` 或其子包 `fleetent.intelligence.memory.shared`。
- public API surface：`SharedMemoryItem`、`create_shared_memory()`、`update_shared_memory()`、
  `archive_shared_memory()`、`search_shared_memory()`、`iter_indexable_shared_memories()`，
  以及 reflection proposal apply 入口。
- owned tables：`shared_memory_items`；proposal 记录若存在，归 reflection owns，本 change 只消费 approved proposal。
- config namespace：无新增配置。
- cross-module dependencies：依赖 `vector_store` public API；reflection 可通过 public apply API 写入；
  long-term-ctx 只在后续 policy spec 中消费。
- migration / shim plan：新增 Alembic migration；不修改 `memory_items` 语义。
