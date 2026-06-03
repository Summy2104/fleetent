# reflection-knowledge-base-reports

## Why

Knowledge Base 已具备 ingest、sync、hybrid retrieval、connector status、source attribution、entity / graph
规划能力，但缺少一个从运行证据出发的质量体检入口。当前 operator 只能看单次检索或 connector 状态，无法系统性回答：
哪些问题经常找不到资料、哪些文档可能过期、哪些 connector 长期失败、实体图覆盖哪里缺口最大。

本 change 让 reflection 生成只读 KB 质量报告。报告只输出 findings 和建议，不自动写入 KB、不触发 sync、不创建
KB 变更 proposal。

## What Changes

- 新增 `run_kb_reflection_report()` public API。
- 新增 `kb_reflection_reports` 表，归 reflection owns。
- 支持 finding 类型：
  - `missing_knowledge`
  - `stale_document`
  - `low_retrieval_quality`
  - `connector_sync_issue`
  - `entity_graph_gap`
- 每条 finding 必须包含 evidence、severity、affected scope 和 recommendation。
- 读取 observability trace / source attribution、KB retrieval、graph/entity 覆盖和 connector latest status 的 public API。
- 提供 deterministic evaluation fixture。

## Out Of Scope

- 不自动创建、更新、删除或归档 KB 文档。
- 不自动触发 connector sync。
- 不创建 KB mutation proposal lifecycle。
- 不要求真实 SaaS connector 或真实 LLM。
- 不做 dashboard UI；管理面只消费报告。

## Module Boundary Impact

- owning package：`fleetent.intelligence.reflection`。
- public API surface：`KnowledgeBaseReflectionReport`、`KnowledgeBaseReflectionFinding`、
  `run_kb_reflection_report()`、report persistence/query API。
- owned tables：`kb_reflection_reports`。
- config namespace：无新增必需配置；真实 smoke 使用显式 env guard。
- cross-module dependencies：只读依赖 observability 和 knowledge-base public APIs；不得直接查询 KB 内部表。
- migration / shim plan：新增 Alembic migration；不改现有 `reflection_reports` 语义。
