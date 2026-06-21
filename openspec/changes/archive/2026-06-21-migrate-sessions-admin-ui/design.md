## Context

C1(已在 main)的 `features/agents/` 是已坐实的"港一个域"范式(`api.ts` TanStack Query hooks via `useAdminApi`;`page.tsx`;MSW 测);域在 `app/routes.tsx` 三处登记,未迁域走 `legacyLinks`。本切片照此港 sessions。注意:chat playground 已在 `prune-platform-dead-debt` 移除——本域**只做会话列表 + 治理**,不重建试聊。

## Goals / Non-Goals

**Goals:** sessions 域原生进 SPA:列表/详情 + 治理动作(接管/释放/注入/强制结束/清空/重置/批量);高危二次确认;viewer 只读;TDD + MSW 覆盖。
**Non-Goals:** 不建 chat playground;不改 session 后端 API(已完整);不动其它域;不引入新依赖。

## Decisions

**D1 · 照 agents 范式。** `features/sessions/api.ts` 暴露 `useSessionsQuery`、`useSessionDetail`、以及治理 mutation(`useTakeover`/`useRelease`/`useInject`/`useForceEnd`/`useClear`/`useReset`/`useBulkAction`),mutation 后失效会话列表/详情。

**D2 · 高危动作二次确认 + 角色门。** force-end / clear / reset / 批量 在 UI 上需二次确认;写动作仅 admin 可见/可用,viewer 只读浏览。测试覆盖确认流与角色门。

**D3 · routes.tsx 唯一共享缝。** 登记 sessions(import + NavLink + Route)。与并行的 providers/users change 仅此文件相撞,机械可解。

## Risks / Trade-offs

- **[与并行域撞 routes.tsx]** → 3 行登记,merge 保留各域条目即可。
- **[误触高危动作]** → 二次确认 + admin 门;测试守这两条。
- **[parity 漏项]** → 以 legacy sessions 区块能力清单逐条对照(列表/筛选、详情、接管/释放/注入/强制结束/清空/重置、批量);playground 明确不在范围。
