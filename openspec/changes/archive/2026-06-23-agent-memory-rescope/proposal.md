## Why

`shared_memory` 是个半成品、且作用域定错了：

- **未接通**：写——批准一条 shared-memory proposal 只 `mark_*_applied` 标状态、**从不调 `create_shared_memory`**（全库零调用方）；读——`build_context` 根本不查它。per-agent home 里的 `shared_memory.db` 是空壳。
- **作用域定错**：它现在被建成 **per-tenant 资源**（`tenant_scope(tenant)` 解析、platform "shared memory 投影 per-tenant 直读"、schema 标 tenant-scoped），但物理上每个 agent home 各一份 → "per-tenant 共享"既没物理共享、scope 模型（team/tenant）也没人消费。

探索结论（见 `docs/architecture/agent-home-layout.md` 目标态 ledger E）：跨 agent / 跨租户的共享知识由 **KB**（受治理）承担；这块记忆应正名为 **agent memory**、收成 **agent 级**——"该 agent 跨其所有 user/session 的非个人化记忆"，三层记忆正交：`per-(agent×user)` user memory / `per-agent` agent memory / `per-tenant 治理` KB。

## What Changes

- **正名**：`shared_memory` → `agent_memory` 全链路（表 `shared_memory_items`→`agent_memory_items`、`create/search/list/iter_*_shared_memory*`→`*_agent_memory*`、`memory/__init__` 导出、向量命名空间、`memory.shared` 写接口名）。
- **重作用域（核心）**：agent memory 从 **per-tenant 资源**改为 **per-agent 资源**——由 `agent_scope(tenant, agent_id)` 解析（不再 `tenant_scope`）；**删除 `scope_type`/`scope_id`（team/tenant）列与 API 参数**，作用域隐式=该 agent；向量命名空间去 scope 维。
- **platform 投影**：agent memory 投影改为 **per-agent 直读**（不再 per-tenant 直读）。
- **reflection**：`suggest_shared_memory_or_kb` 动作术语改 `agent_memory`（**promote-to-KB 这条出路不变**）；维护入口 `apply_shared_memory_proposal`→`apply_agent_memory_proposal`。
- **迁移**：用上线前内测"重建而非迁移"窗口——新嵌入式 forward-only 迁移建 `agent_memory_items`（无 scope 列），旧 `shared_memory` 数据丢弃，**不做数据搬迁**。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `tenant-scoped-db-routing`: agent memory 从 `tenant_scope`（per-tenant）移到 `agent_scope`（per-agent）；`tenant_scope` 的 per-tenant 资源清单去掉"共享记忆"（只剩 KB）。
- `agent-db-schema-self-init`: agent memory schema 由 per-agent `agent_scope` 嵌入式迁移建（不再是 tenant-scoped `shared_memory.db`）；`agent_memory_items` 无 scope 列。
- `platform-read-projection`: agent memory 投影语义由"per-tenant 直读"改为"per-agent 直读"。
- `self-evolution-split`: 审批门回调落地的写接口由 `memory.shared` 正名为 agent memory 写接口（方向/结构不变，仅术语 + 作用域）。
- `manual-maintenance-entrypoints`: Shared Memory 维护入口/proposal apply 正名为 Agent Memory（`apply_agent_memory_proposal`），proposal 生命周期不变。

## Impact

- **owning package**: `memory/`（`shared.py`→`agent_memory.py`、`models.py`、`shared_memory_migrations.py`→`agent_memory_migrations.py`、`proposal_store.py`、`trends.py`、`__init__.py` 导出）。
- **public API surface**: `memory` 模块的 `create_agent_memory` / `search_agent_memory` / `list_agent_memory` / `iter_indexable_agent_memories`（去 scope 参数）；`AgentMemoryItem`（去 scope 字段）。
- **owned tables**: `agent_memory_items`（per-agent，从 `shared_memory_items` 改名 + 删 `scope_type`/`scope_id`）。
- **config namespace**: 若 `config.py` 有 shared-memory 设置项，相应正名/简化（无 scope）。
- **cross-module dependencies**: `tenant_router` 暴露 agent memory 经 `agent_scope`（取代 `tenant_scope.open_shared_memory_db`）；`platform/read_projection` 改 per-agent 只读投影；agent 运行时模块 MUST NOT import platform（铁律），护栏 `test_module_dependency_guardrails` 须仍绿。
- **migration / shim plan**: 嵌入式 forward-only 新版本建 `agent_memory_items`；**不迁移数据**（上线前重建窗口，见 `[[persistence-redesign-roadmap]]` #3）。旧 `shared_memory_*` 符号不留 shim（半成品、无消费者，直接改名净化）。
- **OUT OF SCOPE**：① 把 agent memory 接进 `build_context` 读注入（功能接通，半成品另一半，单独立项）；② tenant-first 整体目录布局重构（另一片）。本片只做"正名 + 重作用域 + 删 scope"。
- 受影响代码：`memory/*`、`tenant_router.py`、`platform/read_projection.py`、`reflection/reflection.py`、`config.py`、`vector_store/reindex.py`、`agent_app._init_agent_db_schema`。
