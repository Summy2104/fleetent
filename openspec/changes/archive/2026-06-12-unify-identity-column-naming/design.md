# unify-identity-column-naming Design

## Context

实体模型细扣（2026-06-12）发现 `approvals.approver_actor` 是 agent_state.db 中唯一不用 `*_user_id` 后缀的身份列。核实事实：写入点 `permission_gate.py:297` 为 `approver_actor=approver_user_id`——代码内部词汇（32 处 `approver_user_id`）早已与拟议列名一致，仅列名落后；改名面 = 3 个源文件（9 处字面量）+ 5 个测试文件 + 1 个 canonical spec。历史：该列原名即 `approver_user_id`，R1（agent-owned-approval）改为 `approver_actor` 并配了 ensure_schema 自愈回填；自愈代码后被 retire-ensure-schema 移除，但 spec requirement 残留至今。

## Goals / Non-Goals

**Goals:**
- agent 侧身份列命名 100% 统一（`*_user_id`），语义契约入文档
- 清掉 standalone-agent-approval 的 ensure_schema 漂移 requirement
- §3.3 一次性补齐四条已裁决的语义注记（多态 target_ref / run_id 命名空间 / session_id 时序 / budget scope 枚举）

**Non-Goals:**
- 不动 `reflection_proposals` 的三个 `*_user_id` 列（已是目标命名）
- 不为旧列名留读兼容（消费方全在本仓，一次改净；上线前窗口）
- 不处理 Y 版本闸之外的遗留双列形态库

## Decisions

**D1：统一方向 = `approver_actor → approver_user_id`（回退 R1 命名，理由链入档）**
R1 当时改名 "actor" 的动机是"Identity 端口落地前，agent 不依赖 platform 身份概念"——用词回避 user 是边界防御。该动机已被两件事取代：#4 identity-port 确立 `Principal{user_id, tenant_id}` 为核与 edge 的唯一身份通货；unify-im-identity-mapping 统一了 user_id 命名空间（managed 内部 id / standalone 渠道原生 id 透传）。如今 "user_id 后缀 = Principal.user_id 字符串" 是全库事实约定（10+ 列），"actor" 反成理解负担。**若将来再有人提议改回 "actor"，须先推翻本段理由链**：即论证 Principal.user_id 不再是统一身份通货。

**D2：Y 新版本用原生 `RENAME COLUMN`，不做表重建（append 在当前最大版本之后，勿硬编码——v29/v30 已被 typed-scheduled-task-delivery 占用，当前应为 v31，以 apply 时实际最大版本为准）**
SQLite ≥3.25 支持（项目基线 Python 3.12 内置 ≥3.45）；该列无索引、无约束、无触发器依赖，RENAME 安全且保数据。统一 Y 谱系下 approvals 由 v12 建表 + 060 修 id 类型……单形态推进，迁移内无需探测分支。

**D3：spec 的家 = standalone-agent-approval**
该 spec 已承载 approvals 表形态类 requirement（"approvals.id column SHALL be TEXT"），新增"审批人列统一命名与语义"与之同类；REMOVED 的 ensure_schema requirement 也在同一文件，一进一出闭环。

**D4：四条语义注记随本 change 写入 §3.3（不另开文档 change）**
同一节、同一主题（实体模型澄清）、均为已与用户裁决过的结论，拆开只产生第二个微型 docs commit。

## Risks / Trade-offs

- [外部消费方引用旧键名] → `/approvals` 端点响应若透出该字段，测试覆盖改名后契约；本仓外无消费方（pilot 前）
- [RENAME 在某些旧 SQLite 上不可用] → 运行基线内置 SQLite 远高于 3.25，不加版本探测
- [全仓还有漏网的 `approver_actor` 字面量] → 收尾 grep 清零断言（含 docs/）

## Migration Plan

Y 新版本随 migrate-on-open 自动执行；forward-only 无回滚（内测窗口可重置）。代码与迁移同 commit 原子落地。

## Open Questions

（无——方向与范围已与用户对齐。）
