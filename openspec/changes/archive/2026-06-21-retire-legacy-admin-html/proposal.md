## Why

legacy 单文件管理台(`static/admin.html` + `/admin/ui-legacy`)当初保留是为"逐域迁移期的回退"。如今**所有域已原生**(agents/providers/users/sessions/kb/skills/connectors/chat/stats/nodes/tenancy)、且 **agent 详情绑定也已原生化**(`agent-bindings-native` 落地)——已核实 **origin/main 前端再无任何 `/admin/ui-legacy` 深链、legacyLinks 也已清空**。共存使命完成,legacy 该退役:删掉 4731 行单文件 + 其托管,消除双前端维护负担与"还有个旧台"的认知噪音。

## What Changes

- 删除 `src/fleetent/static/admin.html`(可经 git 历史恢复)。
- `server.py` 移除 legacy 托管:`LEGACY_ADMIN_UI_PATH`、`_legacy_admin_html`、`@app.get("/admin/ui-legacy")` 路由。`/admin/ui-legacy` 此后返回 404。
- 清理 `routes.tsx` 残留的 `legacyLinks` 脚手架(已为空)及 `routes.test.tsx` 相关断言(若有)。
- 收敛 spec:`admin-frontend-spa` 删除"新旧共存"要求、托管要求去掉 `/admin/ui-legacy` 不遮蔽子句。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `admin-frontend-spa`: 移除"新旧前端共存与切换"要求(legacy 退役);"FastAPI 托管 SPA"要求去掉关于 `/admin/ui-legacy` 的子句(只保留不遮蔽 `/admin/*` API)。

## Impact

- **删除/改动**:`src/fleetent/static/admin.html`(删);`src/fleetent/server.py`(移除 legacy 托管);`frontend/src/app/routes.tsx` + `routes.test.tsx`(清残留 legacyLinks);`admin-frontend-spa` spec。
- **行为变化**:**BREAKING** —— `/admin/ui-legacy` 不再可达(404)。但已核实前端零深链、所有功能在 `/admin/ui` 原生可用,无功能损失。
- **边界**:纯 platform/前端;不碰 agent 运行时、无 schema。
- **⚠️ 排序**:`server.py` 与正在跑的 **G(build-and-serve-frontend-on-deploy)相邻行重叠**(G 改 `ADMIN_UI_DIST_DIR`、D2 删 `LEGACY_ADMIN_UI_PATH`)→ **D2 的 apply 必须排在 G 落地之后**;本 propose 只产 artifacts、现在做不撞。
- **可逆**:admin.html 删除可经 git 恢复;真有遗漏可 revert。
