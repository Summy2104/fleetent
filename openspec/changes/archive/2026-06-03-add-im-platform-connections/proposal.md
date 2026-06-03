## Why

管理员目前无法在后台页面配置 IM 平台连接凭证。后端已有完整的连接器基础设施（`im_connectors` 表、`im_connector_config` 凭证解析与掩码读取、`/admin/im/connectors` 管理 API、连接器管理器启停适配器），但缺三块：(1) 凭证字段 schema 不全（Slack 缺 signing secret，WhatsApp 完全为空）；(2) 没有「新建连接」的 HTTP 入口——`PATCH` 对未 seed 的平台返回 404；(3) admin 控制台没有任何录入凭证的界面。本变更补齐这三块，让管理员能在后台弹窗里按平台填写凭证并启用连接，复用既有连接器存储，不引入新表。

## What Changes

- 扩充 `im_connector_config.PLATFORM_CONFIG_KEYS` 的每平台凭证字段：
  - **Telegram**：`bot_token`
  - **Slack**：`bot_token`（xoxb）、`signing_secret`、`app_token`（socket mode，xapp）
  - **WhatsApp**：`phone_number_id`、`access_token`、`verify_token`、`business_account_id`
- 新增「创建连接」HTTP 入口：`POST /admin/im/connectors`（admin-only），为尚未 seed 的平台 upsert 一行并写入凭证 config（复用 `im_connector_store.upsert_connector` / `im_connector_config.set_config`）。
- admin 控制台新增 IM 连接器管理区：列出各平台连接（status / enabled / 掩码后的凭证），「Add connection」弹窗——platform 下拉（telegram / slack / whatsapp），按所选平台动态渲染对应凭证字段；支持启用/停用。
- 凭证读取走既有掩码视图（只回显末 4 位），原文仅适配器内部 `resolve()` 使用。

非目标（本次不做）：凭证的加密存储（DB-at-rest 加密）。当前凭证存于 `data/users.db`（已 gitignore）、仅 admin 可访问、读取掩码。加密需要先定 on-prem 密钥管理方案，单列为后续变更。

## Capabilities

### New Capabilities
- `im-connector-admin-ui`: admin 控制台录入/查看 IM 平台连接凭证的界面——平台下拉、按平台动态凭证字段、掩码回显、启用/停用、新建连接弹窗。

### Modified Capabilities
- `im-connector-config`: 扩充每平台凭证字段集合（Slack 增 `signing_secret`；WhatsApp 增 `phone_number_id` / `access_token` / `verify_token` / `business_account_id`），并相应补充 `.env` 映射键。
- `im-connector-registry`: 允许通过 admin API 为尚未存在的平台创建连接行（新增 `POST /admin/im/connectors` 创建/初始化路径），使后台弹窗能新增一个全新平台连接。

## Impact

- 代码：
  - `src/fleetent/platform/im_gateway_management/im_connector_config.py`（凭证字段 + .env 映射）
  - `src/fleetent/platform/im_gateway_management/im_admin_api.py`（新增 `POST /admin/im/connectors`）
  - `src/fleetent/static/admin.html`（连接器管理区 + 动态字段弹窗）
- API：`/admin/im/connectors` 新增 `POST`；`GET`/`PATCH`/enable/disable 保持不变。
- 存储：复用既有 `im_connectors` 表与 `config` JSON 列——**不新增表、不新增 Alembic migration**。
- 安全：凭证 admin-only、读取掩码、库文件 gitignored；明文 at-rest 加密留待后续变更。
- 无新依赖；无 ORM；不触碰 agent loop。
