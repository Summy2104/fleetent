## MODIFIED Requirements

### Requirement: FastAPI 托管 SPA 且不遮蔽 API

平台 SHALL 在 `/admin/ui` 托管构建出的 SPA,并对 `/admin/ui` 下的未知子路径回落到 SPA 的 `index.html`(client-side 路由)。该 fallback MUST NOT 遮蔽 `/admin/*` 的 admin API 端点。

#### Scenario: 深链命中 SPA fallback

- **WHEN** 浏览器直接访问 `/admin/ui/agents` 这类 client-side 路由
- **THEN** 平台返回 SPA 的 `index.html`,由前端路由渲染对应页面

#### Scenario: API 不被 fallback 吞掉

- **WHEN** 请求命中某个 `/admin/<resource>` API 端点
- **THEN** 平台返回该 API 本身,而非 SPA 的 `index.html`

## REMOVED Requirements

### Requirement: 新旧前端共存与切换

**Reason**: 所有域已原生(含 agent 详情绑定),前端再无 `/admin/ui-legacy` 深链;共存的过渡使命完成。

**Migration**: 删除 `static/admin.html` 与 `/admin/ui-legacy` 托管;`/admin/ui` 为唯一管理台;旧台经 git 历史可恢复。`/admin/ui-legacy` 此后返回 404。
