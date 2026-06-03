## Why

IM 接入层目前**只能开机静态启动、无法运行时管理**：

1. **连接器无注册、无状态**：Slack / Telegram 适配器在 server lifespan 里硬编码启动，运维看不到"哪个平台连上了没、最近心跳、断线重连状态"。`platform.md` 的「系统健康仪表盘」承诺展示各 IM 平台连接状态，但底层没有可读的连接器状态源。
2. **channel 白名单只是文档承诺、无实现**：`platform.md` 场景 25「新 IM 用户首条消息只要所在 channel 已被部署方配置允许就放行」依赖一个 channel 白名单载体，反复声明"由 im-gateway 域维护"，但代码里并不存在；当前任何 channel 的消息都会进入管线。
3. **平台不能运行时启停**：要停用某个 IM 平台只能改 `.env` 删 token 再重启整个服务，没有"禁用 Slack 但保留 Telegram"的运行时开关。
4. **令牌散在 `.env`、不可在后台管理**：`slack_bot_token` / `telegram_bot_token` 等只能 ssh 改文件，外部控制台 / Admin UI 无法查看（即便脱敏）或更新。

这是 `platform.md` Admin 后台「IM 连接状态」「channel 白名单」「平台启停」三块功能的运行时底座缺口。

## What Changes

按 capability 拆分，便于增量验收：

**ADDED**
- `im-connector-registry`：`im_connectors` 表 + 连接器生命周期管理器（supervisor）。每个 IM 平台作为一个连接器登记（platform、enabled、status、last_heartbeat、last_error）；适配器运行时上报连接 / 心跳 / 断线 / 重连状态；admin 可**运行时启用 / 禁用**某平台（禁用 = 断开且不接消息），无需重启服务。平台无关框架，当前内置 slack / telegram，**whatsapp 留占位**（登记但标 `unconfigured`）。
- `im-channel-allowlist`：`im_channel_allowlist` 表存被允许的 `(platform, scope_type, scope_id)`（channel 或 workspace 粒度）；路由前强制校验，落实 `platform.md` 场景 25。**按平台 opt-in**：连接器未开启 `allowlist_enforced` 时放行全部（兼容当前 MVP 行为），开启后仅放行白名单内的 channel / workspace。admin API + CLI 做 CRUD。
- `im-connector-config`：连接器配置（token 等）可存入 `im_connectors.config`（DB），适配器优先读 DB、回退 `.env`；提供一次性 `seed-connectors` 把现有 `.env` 令牌迁入 DB；API / CLI 读取时**令牌脱敏**（只显示尾 4 位），原值仅适配器内部使用。

**MODIFIED**
- `im-gateway`：Slack / Telegram 适配器接入连接器框架——启动 / 停止由 supervisor 驱动；上报 `status` / `heartbeat` / `last_error` 到注册表；从 `im-connector-config` 解析令牌；路由前调用 `im-channel-allowlist` 校验。`NormalizedMessage` 与 thread-first 等既有契约不变。

## Capabilities

### New Capabilities

- `im-connector-registry`
- `im-channel-allowlist`
- `im-connector-config`

### Modified Capabilities

- `im-gateway`

## Impact

- **代码**：
  - 新增：`im_connector_store.py`（`im_connectors` 表读写 + 状态上报）、`im_connector_manager.py`（adapter 生命周期 supervisor：start / stop / reload）、`im_channel_allowlist.py`（白名单表 + 校验）、`im_admin_api.py`（FastAPI `/admin/im/*` 路由）
  - 修改：`im_gateway/slack.py`、`im_gateway/telegram.py`（接入 supervisor + 状态上报 + 从 DB 取 config）、`im_gateway/normalizer.py`（route 前置 channel 白名单校验）、`server.py`（lifespan 改为经 manager 启动 enabled 连接器、mount admin router）、`admin.py`（新增 im-connector / im-channel CLI 命令）、`config.py`（令牌字段保留作为 fallback）
- **依赖**：无新增依赖（slack-bolt、python-telegram-bot、FastAPI、stdlib sqlite3 均已在）。
- **数据**：`data/users.db` 新增 `im_connectors`、`im_channel_allowlist` 两张表；`seed-connectors` 一次性把 `.env` 中的 slack / telegram 令牌写入 `im_connectors.config` 并按是否有令牌置 `enabled`。令牌明文存于本机 SQLite（与 `.env` 同等信任边界，遵守数据不出内网），API / UI 一律脱敏。
- **认证依赖**：`/admin/im/*` 复用 `agent-admin-api` change 引入的 `users.is_admin` 守卫；若该 change 尚未合入，本 change 在实施时需先确保 admin 守卫存在（见 tasks 0.x 前置检查）。
- **破坏性**：
  - `.env` 中的令牌不再是唯一来源——`seed-connectors` 后以 DB 为准、`.env` 仅作 fallback；未运行 seed 时行为与现状一致（继续读 `.env`）。
  - 启用 `allowlist_enforced` 的平台，**未在白名单内的 channel 消息将被拒**；默认不启用，保持现状放行。

## Commit 切分建议

按 capability 拆，每个 commit 自包含可单独 review，内部仍 TDD（测试先红 → 实现 → 绿）：

1. `feat(im_connector_store): im_connectors table + status reporting`（1.x）
2. `feat(im_connector_config): DB config resolution with .env fallback + seed`（2.x）
3. `feat(im_channel_allowlist): allowlist table + enforcement helper`（3.x）
4. `feat(im_connector_manager): adapter lifecycle supervisor`（4.x）
5. `refactor(im_gateway): adapters report status + load DB config + allowlist check`（5.x）
6. `feat(server): manager-driven lifespan + mount /admin/im router`（6.x）
7. `feat(im_admin_api): /admin/im connectors + allowlist REST`（7.x）
8. `feat(admin): im-connector / im-channel CLI commands`（8.x）
