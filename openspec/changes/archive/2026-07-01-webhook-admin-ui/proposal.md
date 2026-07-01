## Why

托管 webhook source(`webhook_admin_api.py` 的 `/admin/webhooks/sources` CRUD)已上线，但只有后端 REST API，没有管理前端——管理员目前只能直接调接口增删 webhook source，容易出错，也没有自助入口。

## What Changes

- 新增 `features/webhooks/`（`api.ts` + `page.tsx` + `page.test.tsx`），照 `/mcp` 页面范式（TanStack Query + MSW + TDD）。
- 页面支持：列表 `GET /admin/webhooks/sources`、新建 `POST /admin/webhooks/sources`（含 secret 随机生成）、删除 `DELETE /admin/webhooks/sources/{id}`（带确认）。**不支持编辑**——后端 `put_source()` 是"给什么存什么"的 upsert 语义，若允许编辑但漏填 secret 会静默清空已有密钥；本次不新增后端接口，改配置 = 删除重建。
- 表单字段：`id`（创建后不可改）、`agent_id`（前端强制必填——后端模型允许 null，但入站请求在 `agent_id` 为空时会 409，前端把它当必填避免建出打不通的 webhook）、`user_id`（下拉选现有用户）、`reply_target`（可选，下拉选现有用户 + "无"）、`message_template`（可选文本，附占位符语法说明）、`enabled`（开关，默认开）、`secret`（文本框 + 随机生成按钮）。
- 创建成功后展示 `${window.location.origin}/webhook/{id}` 完整地址 + 复制按钮，附一行提示：反向代理/独立域名部署需自行替换域名部分。
- 在 `app/routes.tsx` 注册路由、`app/nav.ts` 的 `integrations` 分组加导航项、`i18n/messages.ts` 补 en + zh 词条。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `webhook-source-management`：新增"managed webhook source 在 React SPA 中原生管理（列表/新建/删除）"——此前只有后端 admin REST API，无前端入口。

## Impact

- **新增**：`frontend/src/features/webhooks/`（api/page/test）。
- **改动**：`frontend/src/app/routes.tsx`（注册路由）、`frontend/src/app/nav.ts`（加导航项）、`frontend/src/i18n/messages.ts`（补词条）。
- **后端**：不改（`/admin/webhooks/sources` 的 GET/POST/DELETE 已完整，足够支撑本次范围）。
- **边界**：纯 `frontend/`；不碰 agent 运行时、`server.py`、schema、迁移。
