# descope-context-policy Tasks

> 删除类 change 的 TDD：先写守护断言（模块/表/导出/API 已不存在）+ 活路径仍工作的测试见红，再删实现见绿。

## 1. 表退役（Alembic）

- [x] 1.1 [测试] integration：管理库 alembic 升到 head 后 `long_term_context_policies` 表**不存在**；含存量行的旧库升级后该表被 drop（先红：当前表存在）
- [x] 1.2 [实现] 新增 alembic 迁移（编号 append after 080、勿硬编码）：`DROP TABLE long_term_context_policies`；downgrade 按 031 原 DDL 重建空表 → 1.1 转绿

## 2. 删模块 + __init__ 收口

- [x] 2.1 [测试] unit：守护——`fleetent.long_term_ctx._policy` 不可导入；`long_term_ctx` 不再导出 `AgentContextIdentity` / `ContextPolicy` / `ContextPolicySourceBudget` / `ContextPolicyRecord` / `resolve_context_policy` / `build_context_with_policy` / `get_policy` / `upsert_policy`；**仍导出 `build_context` / `BudgetPolicy` / `ContextSource` / `BuiltContext`**（先红）
- [x] 2.2 [实现] 删 `src/fleetent/long_term_ctx/_policy.py`；`__init__.py` 去掉 `import _policy` 与 `_policy` 系 re-export，**逐行确认未碰 `build_context`/`_resolve_policy`/`BudgetPolicy`/`ContextSource`/`BuiltContext`** → 2.1 转绿

## 3. 活路径回归 + 删测试

- [x] 3.1 [测试] integration：活的长期上下文组装仍工作——`build_context(user_id, query, agent_name, max_tokens)` 经 `_resolve_policy` → `BudgetPolicy` 正常产出（memory + KB 源、budget 元数据），对照 main 基线无新增失败（确认没误伤）
- [x] 3.2 [实现] 删 5 个测试文件：`tests/unit/test_long_term_ctx_policy_context.py`、`tests/unit/test_long_term_ctx_policy_validation.py`、`tests/integration/test_long_term_ctx_policy_resolution.py`、`tests/integration/test_long_term_ctx_policy_store.py`、`tests/evaluation/test_long_term_ctx_policy_eval.py`；其余 long-term-ctx 测试（活路径）保持绿

## 4. 文档

- [x] 4.1 `docs/architecture/data-model.md` §3.2：管理库实体清单去掉 `long_term_context_policies`；erDiagram 删两条边 `tenants ||--o{ long_term_context_policies` 与 `agents ||--o{ long_term_context_policies`
- [x] 4.2 复核 `docs/capabilities/long-term-ctx.md`（若有）对上下文策略表的描述，去掉/改为活的 BudgetPolicy 口径
- [x] 4.3 `docs/records/decision-logs/`：追记 descope 决策（为什么砍：休眠未接线；活 BudgetPolicy 路径保留；shared-memory 进 context 门控一并 descope、本就没通、可日后重做）

## 5. 收尾

- [x] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [x] 5.2 全仓 grep 清零：`_policy`（long_term_ctx 相关）、`resolve_context_policy`、`AgentContextIdentity`、`long_term_context_policies`（alembic 历史 drop 与 openspec 归档除外）
- [x] 5.3 `openspec validate descope-context-policy` 通过；所有 checkbox 标记 `[x]`
