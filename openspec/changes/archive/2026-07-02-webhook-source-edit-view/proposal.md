## Why

托管 webhook source 的管理前端（`features/webhooks/`）已上线，但**新增后只能在列表看到一小部分字段**（id / agent / user / 启用状态），管理员：

- 看不到自己填的 `reply_target`、`message_template`、是否设了密钥——尽管列表接口其实**已经把这些字段都返回了**，只是页面没展示；
- 无法编辑——上一个 webhook-admin-ui 变更（见其 D2）特意不做编辑，因为后端 `put_source()` 是「给什么存什么」的 upsert，编辑时漏填 secret 会**静默清空已有密钥**。

本次补齐「查看全部字段（密钥除外）」和「安全编辑」两件事。

## What Changes

- **后端新增编辑接口** `PUT /admin/webhooks/sources/{source_id}`：更新 `user_id` / `agent_id` / `message_template` / `reply_target` / `enabled`，外加密钥动作 `secret_action`（`keep` 默认保持原样 / `set` 用新值加密覆盖 / `clear` 置空），彻底避开 upsert 清空密钥的坑。`id` 不可改（它是公开 URL `/webhook/{id}`）。找不到 → 404。响应沿用 `_public_view`（含 `has_secret`，**永不回显明文 secret**），并写 `webhook.update` 审计。
- **store 新增** `update_source(...)`：做 `UPDATE`（非 upsert），常规字段照写；密钥列按 `secret_action` 决定「不动 / 加密写入 / 置 NULL」。
- **前端** `features/webhooks/`：每行操作菜单加「查看/编辑」入口，打开一个弹窗——**默认只读态**展示除密钥外全部字段（reply_target / agent 显示名称而非 id，密钥显示「已设置/未设置」）；点「编辑」切到可改态，`id` 只读，密钥区提供「更换密钥」（展开输入框 + 生成按钮）和「清除密钥」两个显式动作。保存调 PUT，成功后刷新列表并切回只读态。
- `api.ts` 新增 `useUpdateWebhookSourceMutation(id)` 与 `WebhookSourceUpdateInput` 类型；`i18n/messages.ts` 补 `webhooks.*` 新词条（en + zh）。
- **不加**单独的 GET 单条详情接口：列表接口已返回除密钥外全部字段，前端弹窗直接用列表行数据（YAGNI）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `webhook-source-management`：
  - admin REST API 的「更新」从口径存在但无端点，落地为**保留 secret 语义**的 `PUT /admin/webhooks/sources/{id}`（`secret_action` keep/set/clear）。
  - React SPA 从「列表 + 新建 + 删除，明确不支持编辑」升级为「列表 + 新建 + **查看全部字段** + **安全编辑** + 删除」。

## Impact

- **新增**：`PUT /admin/webhooks/sources/{id}` 端点、`webhook_source_store.update_source()`。
- **改动**：`webhook_admin_api.py`（加 PUT 端点 + update body 模型）、`webhook_source_store.py`（加 `update_source`）、`frontend/src/features/webhooks/{api.ts,page.tsx}`、`frontend/src/i18n/messages.ts`。
- **不改**：`webhook_sources` 表结构（字段已够，无迁移）、入站 `webhook_inbound_api.py`、`webhook_router.py`、agent 运行时。

## 模块边界影响声明

- **Owning package**：`fleetent.platform.webhook_management`（平台控制面）+ `frontend/src/features/webhooks`。
- **Public API surface**：新增 `PUT /admin/webhooks/sources/{id}`（admin 鉴权）；store 新增 public `update_source(...)`。响应契约不变（`_public_view`，无明文 secret）。
- **Owned tables**：`webhook_sources`（管理库，Alembic 113 已建）——**本次无 schema 变更、无迁移**。
- **Config namespace**：无。
- **Cross-module dependencies**：沿用现有 `fleetent.db` / `fleetent.secret_crypto` / `fleetent.audit_log` / `fleetent.auth` / `fleetent.user_store`；不新增跨包依赖，不引入 agent→platform 反向依赖。
- **Migration / shim plan**：无迁移、无 shim。
