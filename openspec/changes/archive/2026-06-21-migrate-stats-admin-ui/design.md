## Context

C1 港域范式(`features/agents/`)已坐实;域在 `routes.tsx` 三处登记,未迁域走 `legacyLinks`(Statistics 现为其中唯一剩项,锚点 `#stats`)。本切片照此港 Statistics——它是只读分析 + 导出,无写操作。

## Goals / Non-Goals

**Goals:** Statistics 原生进 SPA,与 legacy #stats parity(per-agent overview / per-user / compare / 请求·会话 trace / 导出);TDD + MSW。
**Non-Goals:** 不改 stats 后端 API;不调已删的 `/stats/reports`;不动其它域;不引入新依赖。

## Decisions

**D1 · 照 agents 范式,只读为主。** `features/stats/api.ts` 以 TanStack Query 暴露各只读查询(overview/compare/tools/per-user/user-requests/request-detail/session-trace);导出 `POST /export` 触发下载(fetch + blob 或返回内容渲染)。无 mutation-失效复杂度(只读)。

**D2 · routes.tsx 共享缝。** 注册 stats + 从 `legacyLinks` 删 Statistics(删后 legacyLinks 为空)。`routes.test.tsx` 用 `within(nav)` scope。

## Risks / Trade-offs

- **[导出形态]** → `POST /export` 可能返回 CSV/JSON blob;前端按响应 content-type 处理下载,测试覆盖触发与文件名。
- **[parity 漏项]** → 以 legacy #stats tab 能力逐条对照。
- **[与同期前端域撞 routes.tsx]** → 合并由主会话串行做,保留各域条目。
