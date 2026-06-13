# descope-context-policy Design

## Context

`long_term_ctx/_policy.py`（ContextPolicy/AgentContextIdentity/ContextPolicyRecord + resolve/get/upsert）读管理库表 `long_term_context_policies`（Alembic 031 建、070 加 FK）。已核实：① 读它的链生产零调用方（`build_context_with_policy` / `resolve_context_policy` / `get_policy` / `upsert_policy` 仅测试调）；② 活路径是 `__init__.py` 的 `build_context` → `_resolve_policy(available_tokens)` → `BudgetPolicy`（`__init__.py:74`），与 `_policy.py` 无关；③ 表里 `agent_id` 存 agent name。当前 alembic head = 080。同 layered budget/reflection 半成品的"建好没接"。

## Goals / Non-Goals

**Goals:**
- 移净休眠的上下文策略（表 + `_policy.py` + 导出 + 测试 + spec requirement）
- 活的长期上下文（build_context / _resolve_policy / BudgetPolicy / memory+KB 组装）行为零变化
- 决策与"shared-memory 进 context 门控被一并 descope"留档、可逆

**Non-Goals:**
- 不碰活路径：`build_context`、`_resolve_policy`、`BudgetPolicy`、`ContextSource`、`BuiltContext`（均在 `__init__.py`）
- 不动 shared-memory 的写/读（`memory/shared.py`、read projection）——只移除其"进 context"的未接门控设计
- 不留 stub/flag——干净删除，重建从 git 历史取（同 descope-layered-budget 的 D1）

## Decisions

**D1：整删不留 stub**（同 layered budget）：保留半截只会变成下轮审计的"build-but-unwired"。模块/表/导出/测试/spec 一并移除。

**D2：表 drop 走 Alembic（管理库 schema），编号 append after 080、不硬编码**：`DROP TABLE long_term_context_policies`，downgrade 重建空表（列定义抄 031）。存量行丢弃（休眠多为空、上线前窗口）。

**D3：`__init__.py` 外科式收口**：只删 `import _policy` 与 `_policy` 系 re-export（AgentContextIdentity/ContextPolicy/ContextPolicySourceBudget/ContextPolicyRecord/resolve_context_policy/build_context_with_policy/get_policy/upsert_policy）；逐行确认 `build_context`/`_resolve_policy`/`BudgetPolicy`/`ContextSource`/`BuiltContext` 不在删除集。

**D4：shared-memory 门控的处置**：此休眠策略含"shared-memory 按 policy 进 context"的设计；它未接线（活路径 `_resolve_policy` 只覆盖 memory+KB，无 shared-memory 预算）。descope 后 shared-memory 进 context 这条路正式移除（行为不变，本就没通）。shared-memory 本体存储/读不动。

## Risks / Trade-offs

- [误删活路径依赖] → 已核 `_resolve_policy` 返回 `BudgetPolicy`（非 `_policy.py` 的 ContextPolicy）、活路径零依赖 `_policy`；守护测试断言 build_context 仍工作、`_policy` 不可导入
- [`__init__.py` re-export 有外部消费方] → 全仓 grep（src 排除 _policy.py/__init__.py）零生产消费，仅测试；删测试一并处理
- [drop 表后某处仍查] → 全仓 grep `long_term_context_policies` / `resolve_context_policy` / `AgentContextIdentity` 清零（alembic 历史 drop 除外）
- [shared-memory 其实有别的进-context 路径被波及] → 已确认活 `_resolve_policy` 不含 shared-memory；本 change 不碰 memory/shared.py

## Migration Plan

Alembic 081 `DROP TABLE long_term_context_policies`（forward-only，downgrade 重建空表）。代码删除与迁移同 change。回滚 = git revert + 库重置（上线前窗口）。

## Open Questions

（无——descope、活路径保留、shared-memory 门控一并 descope 已与用户对齐。）
