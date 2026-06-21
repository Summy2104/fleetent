## Why

Statistics 是最后一个仍深链回 legacy(`#stats`)的有 tab 的域。把它迁成新 SPA 原生页,标准 2(平台管理面 UI)的"有 legacy tab 的域"就全原生了。

## What Changes

- 新增 `features/stats/`(`api.ts` + `page.tsx` + `page.test.tsx`),照 C1 agents 范式(TanStack Query + MSW + TDD)。
- 覆盖既有 admin API(`/admin/stats`,均为只读 + 导出):per-agent overview `GET /agents/{id}/overview`、对比 `GET /compare`、工具 `GET /agents/{id}/tools`、per-user `GET /per-user`、用户请求 `GET /users/{id}/requests`、请求详情 `GET /requests/{id}`、会话 trace `GET /sessions/{id}/trace`、导出 `POST /export`。
- 在 `app/routes.tsx` 注册 stats 路由 + 导航,并从 `legacyLinks` 移除 Statistics(legacyLinks 随之清空)。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `stats-admin-ui`: 新增"Statistics 域在 React SPA 中原生渲染(per-agent overview / per-user / compare / 请求·会话 trace / 导出),从 legacy 深链改为原生路由"的要求。

## Impact

- **新增**:`frontend/src/features/stats/`(api/page/test)。
- **改动**:`frontend/src/app/routes.tsx`(注册 stats + 从 legacyLinks 移除 Statistics)——共享缝,机械可解。
- **后端**:不改(stats admin API 已完整;prune 已移除不存在的 `/stats/reports`,本域不调它)。
- **边界**:纯 `frontend/`;不碰 server.py / agent / schema。建在 C1 壳上。**合并由主会话串行做。**
