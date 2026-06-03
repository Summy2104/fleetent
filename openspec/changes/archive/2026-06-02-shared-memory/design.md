# Design

## 定位

Shared Memory 是 User Memory 之外的独立共享语义记忆。它保存“确认过、短小、结构化、适合直接作为上下文”的
共享信息，例如团队惯例、租户级背景、项目默认偏好。它不是 KB 文档，也不是从普通用户对话自动抽取的个人事实。

第一版不让 Agent 自动注入 Shared Memory；它只提供可依赖的数据层、检索层、reindex 边界和受控写入入口。
后续 `long-term-context-agent-tenant-policy` 再决定哪些 agent / tenant 使用 Shared Memory、预算如何分配、冲突时谁优先。

## Data Model

`shared_memory_items`：

- `id`
- `scope_type`: `team` 或 `tenant`
- `scope_id`
- `type`: `context`、`preference`、`procedure`
- `content`
- `status`: `active`、`stale`、`archived`
- `source`: `manual`、`reflection_proposal`
- `source_ref`
- `created_by`
- `created_at`
- `updated_at`

唯一性不强制按 content 去重。第一版只提供 exact duplicate helper 或维护接口，不自动合并语义相近内容。

## Public API

- `create_shared_memory(scope_type, scope_id, type, content, created_by, source="manual", source_ref=None)`
- `update_shared_memory(item_id, content=None, type=None, status=None)`
- `archive_shared_memory(item_id)`
- `search_shared_memory(scope_type, scope_id, query, limit)`
- `iter_indexable_shared_memories(scope_type, scope_id)`
- `apply_shared_memory_proposal(proposal_id, actor_id)` 或等价 public apply 入口

所有 API 通过 store 边界访问 SQLite，SQL 使用 named parameters。创建和更新 active/stale item 时同步
`vector_store.upsert()`；归档时 `vector_store.delete()`。

## Reflection Proposal Boundary

reflection 仍然负责生成 pending proposal 和审批状态。Shared Memory 只接收 approved proposal 的 apply 请求：

1. 校验 proposal target 为 `shared_memory`。
2. 校验 scope、type、content 合法。
3. 创建或更新 `shared_memory_items`。
4. 回写 apply result 给 reflection public API，或返回 apply summary 由 reflection 调用方回写。

## Admin/API

第一版需要最小维护入口，避免只能通过测试写数据：

- list/search shared memory by scope
- create/update/archive
- apply approved proposal

写操作需走 admin 权限和 audit log；若 admin API 依赖未就绪，可以先提供 `fleetent-admin memory shared ...`
CLI，但 spec 应保留 HTTP 管理面边界。

## Evaluation

默认 evaluation 使用 deterministic embedding、tmp SQLite 和 fake vector backend，验证：

- scope isolation；
- active/stale 可被检索，archived 不可被检索；
- procedure/preference/context 均能进入 index；
- proposal apply 后可检索。

不接真实 LLM 或真实 embedding provider。
