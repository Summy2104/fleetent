# descope-context-policy

## Why

`long_term_context_policies`（per-tenant/agent 的长期上下文源策略表）+ `long_term_ctx/_policy.py` 整套是一个**完整建好、有测试、但生产零接线**的休眠功能：读它的链（`build_context_with_policy` / `resolve_context_policy` / `get_policy` / `upsert_policy`）在 `src/` 里没有任何生产调用方，只有测试调。生产的长期上下文走的是另一条独立路径——`build_context` → `_resolve_policy(available_tokens)` → `BudgetPolicy`（按 token 预算，定义在 `__init__.py`），完全不碰这张表。它还是平台侧"三个字符串型 `agent_id` 偏离者"之一（VARCHAR 存 agent name），但因休眠故类型问题 moot。继 layered budget、reflection 半成品之后的同款"建好没接"，v1 直接砍、简化、可日后重做。

## What Changes

- **drop 表**：新 Alembic 迁移（编号在当前最大 080 之后、不硬编码）`DROP TABLE long_term_context_policies`（管理库，031 建、070 加 FK）
- **删模块**：`long_term_ctx/_policy.py` 整个移除（`ContextPolicy` / `ContextPolicySourceBudget` / `AgentContextIdentity` / `ContextPolicyRecord` / `resolve_context_policy` / `get_policy` / `upsert_policy` / `build_context_with_policy` 及内部 helper）
- **收口 `__init__.py`**：去掉对 `_policy` 的 import 与 re-export；**保留活路径 `build_context` / `_resolve_policy` / `BudgetPolicy` / `ContextSource` / `BuiltContext`（全在 `__init__.py`，不动）**
- **删测试**：`test_long_term_ctx_policy_{context,validation,resolution,store,eval}` 5 个文件
- **文档**：`data-model.md` §3.2 管理库清单 + erDiagram 去掉 `long_term_context_policies`（连两条边 `tenants→`/`agents→`）；decision-log 追记 descope
- 落地**一步到位**

**诚实影响**：这条休眠策略里含 **shared-memory 进 long-term-context 的门控设计**（"Shared Memory requires explicit policy" 等场景）——它本就没接线，所以 shared-memory 注入 context 这条路**生产中本就没通**。砍掉 = 把这个未接的设计一并 descope：**当前行为不变**（已是 dormant）；shared-memory 的写/读本身（`memory/shared.py`、`read_projection`）**不受影响、仍在**。日后若要"shared-memory 进 context"需重新设计。

## Capabilities

### Modified Capabilities

- `long-term-ctx`: REMOVE "Agent tenant context policy design"（per-tenant/agent 上下文源策略，含 shared-memory 门控）——休眠未接线功能 v1 descope；保留活的 BudgetPolicy token 预算路径相关 requirement（Deterministic budget policy / Source budget limits / Source-aware conflict preference / Budget decision metadata / Conservative policy scope 等不动）

## Impact

- **owning package**：`long_term_ctx`（删 `_policy.py` + `__init__` 收口）、`platform`（Alembic 迁移）
- **public API surface**：`long_term_ctx` 移除 `_policy` 系导出（`AgentContextIdentity` / `ContextPolicy` / `ContextPolicySourceBudget` / `ContextPolicyRecord` / `resolve_context_policy` / `build_context_with_policy` / `get_policy` / `upsert_policy`）；`build_context` / `BudgetPolicy` / `ContextSource` / `BuiltContext` 不变
- **owned tables**：管理库 drop `long_term_context_policies`（Alembic 081）
- **config namespace**：无（活路径的 `LongTermContextSettings` 不变）
- **cross-module dependencies**：不碰 agent 零 platform import；活的长期上下文组装（memory + KB）不变
- **migration / shim plan**：Alembic drop（forward-only，存量行丢弃——休眠表多为空、上线前窗口）；无代码 shim
- **相邻切片**：已确认 5 个在跑 change（conversation-address / delivery-receipts / kb-standalone / trace-tool-spans / unified-file-exchange）均不碰 long_term_ctx
