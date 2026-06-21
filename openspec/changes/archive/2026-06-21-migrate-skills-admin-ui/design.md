## Context

C1(已在 main)的 `features/agents/` 是已坐实的港域范式;域在 `app/routes.tsx` 三处登记,未迁域走 `legacyLinks`(Skills 现为其中一条)。本切片照此港 skills。注意:技能提案审批是 agent-owned、经 DM(`prune-platform-dead-debt` 已删平台 approve/reject 桩),所以 SPA 提案区**只读**(列表 + diff)。

## Goals / Non-Goals

**Goals:** skills 域原生进 SPA,与 legacy #skills tab parity(列表/内容/启停/删恢复/强发/重扫/agent 绑定/版本 diff)+ 提案只读查看;TDD + MSW。
**Non-Goals:** 不做提案 approve/reject(agent-owned,平台桩已删);不改后端 skill API;不动其它域;不引入新依赖。

## Decisions

**D1 · 照 agents 范式。** `features/skills/api.ts` 暴露 skills 的 query/mutation hooks(list、content、enable/disable、delete/restore、force-publish、reload、agent 绑定、versions/diff)+ 提案只读 hooks(proposals 列表、proposal diff)。mutation 后失效相关列表。

**D2 · 提案区只读。** 列出提案 + 看 diff,**不渲染 approve/reject**;若运维想批准,提示走 agent DM 审批流(平台只读投影)。测试断言无 approve/reject 控件。

**D3 · routes.tsx 唯一共享缝。** 注册 skills + 从 `legacyLinks` 删 Skills。与同批 kb/connectors 仅此文件相撞。

## Risks / Trade-offs

- **[与同批域撞 routes.tsx]** → 保留各域条目 + 各自删自己 legacy link。
- **[误以为该有 approve/reject]** → 明确只读;测试守"无 approve/reject 控件",与 prune 的决策一致。
- **[parity 漏项]** → 以 legacy #skills tab 能力逐条对照(列表/内容/启停/删恢复/强发/重扫/绑定/版本 diff/提案查看)。
