## Why

fleetent 需要企业知识库能力，但团队已经有独立项目 `knowledge-bridge`，其中包含大量可复用经验：
parser、connector、sync planner、hybrid retrieval、retrieval audit、query scope 和运维工具。

直接把 `knowledge-bridge` 作为依赖不合适，因为它当前依赖 LlamaIndex、LanceDB、OpenAI Embeddings、
Poetry/runtime home 等模式，和 fleetent 的约束不一致：

- fleetent 禁止引入 LlamaIndex / LlamaIndex 风格框架。
- fleetent 要使用自有 `vector_store` 边界，不直接接 LanceDB。
- fleetent 禁止云托管 Embeddings 作为默认能力。
- fleetent 使用 OpenSpec、Alembic、database-runtime 和 modular monolith 边界。
- fleetent 的知识库身份是 `tenant_id + kb_id`，并要服务 long-term-ctx。

因此，knowledge-base 不应从一个“大 spec”开始实现，而应先做迁移评估与拆分计划。

## What Changes

- 新增一个 doc-only OpenSpec change，用于产出 `knowledge-bridge` 到 fleetent 的迁移计划。
- 盘点 `knowledge-bridge` 的模块和能力：
  - parser
  - connector
  - sync planner
  - retrieval
  - metadata store
  - audit
  - query scope / KB registry
- 分类每块能力：
  - 可直接迁移
  - 可参考但需重写
  - 暂缓迁移
  - 不迁移
- 输出 fleetent knowledge-base 后续 specs 拆分和推荐顺序。
- 明确第一批 implementation spec 的最小范围与依赖。

## Capabilities

### New Capabilities

- 无新增运行时能力。本 change 只产出迁移计划。

### Modified Capabilities

- `knowledge-base`：补充 migration plan，明确如何从 `knowledge-bridge` 继承资产并拆分后续工作。

## Impact

- **代码**：无。
- **数据库**：无。
- **依赖**：无新增运行时依赖。
- **文档**：
  - 新增 `docs/knowledge-bridge-migration-plan.md` 或等价文档。
  - 更新 `docs/capabilities/knowledge-base.md` 的计划链接和拆分路线。
- **不包含**：
  - 不迁移任何 parser / connector 代码。
  - 不实现 knowledge-base tables。
  - 不实现 ingest/search。
  - 不引入 LlamaIndex、LanceDB、OpenAI Embeddings、docling 等依赖。
