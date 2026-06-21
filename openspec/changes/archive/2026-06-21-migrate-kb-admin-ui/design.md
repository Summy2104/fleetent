## Context

C1(已在 main)的 `features/agents/` 是已坐实的港域范式(`api.ts` TanStack Query via `useAdminApi`;`page.tsx`;`page.test.tsx` MSW);域在 `app/routes.tsx` 三处登记,未迁域走 `legacyLinks`(KB 现为其中一条)。本切片照此港 KB,并补齐 legacy 也缺的内容生命周期 UI。KB 是本批最大的域(库 + 文档 + 连接器三块)。

## Goals / Non-Goals

**Goals:** KB 域原生进 SPA:库 CRUD、文档灌入/列表/删除/同步、KB 连接器(注册/检查/状态/同步)、agent 绑定查看;TDD + MSW。
**Non-Goals:** 不改 KB 后端 API(已完整);不动其它域;检索 playground / extract-entities / observation 为可选增强,非本切片必须;不引入新依赖。

## Decisions

**D1 · 照 agents 范式,三块组织。** `features/kb/api.ts` 暴露 库 hooks(list/create/update/delete)、文档 hooks(ingest/list/delete/sync)、连接器 hooks(list/create/update/delete/check/status/sync),mutation 后失效相关列表(`['kb']`、`['kb', id, 'documents']` 等)。`page.tsx` 库列表 + 详情(文档面板 + 连接器面板)+ 各操作弹窗/确认。

**D2 · 内容生命周期是本切片重点。** legacy 灌文档/同步只能 API/CLI;本域必须让运维在页面上灌入文档、看列表、删除、触发 sync,并管理 KB 连接器(注册 + 检查 + 状态 + 同步)。

**D3 · routes.tsx 唯一共享缝。** 注册 kb(import + NavLink + Route)并从 `legacyLinks` 删 Knowledge Base。与同批 skills/connectors 仅此文件相撞,保留各域条目即可。

## Risks / Trade-offs

- **[与同批域撞 routes.tsx]** → 注册 + 删自己那条 legacy link;merge 时保留各域条目。
- **[KB 域偏大,测试面广]** → 三块(库/文档/连接器)分别 TDD,MSW 覆盖各端点的成功/失败/失效刷新;parity 以 legacy #kb tab 能力逐块对照。
- **[长耗时操作(sync/ingest)]** → UI 给出进行中/结果反馈,mutation 后失效列表;不阻塞页面。
