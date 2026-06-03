# Design — IM Gateway Management

## 范围与边界

本 change 只做 IM **连接器层**（platform / channel 粒度）的运行时管理，与既有的 `im-user-allowlist`（per-user 审批）正交：

- `im-channel-allowlist`：决定"**哪个 channel / workspace 的消息可以进系统**"——粗粒度准入。
- `im-user-allowlist`：决定"**哪个 IM 用户被允许**"——细粒度准入（v1.0 起在允许的 channel 内默认放行）。

路由校验顺序：**channel 白名单 → user 白名单 → agent 解析**。

## 连接器生命周期（supervisor）

`im_connector_manager` 持有每个平台的运行任务（`asyncio.Task`），对外暴露：

```
start(platform)   # 读 config，启动该平台 adapter，置 status=connecting
stop(platform)    # 取消 adapter 任务，释放连接，置 status=stopped
reload(platform)  # stop 后 start，用于改 config / 重连
running() -> set[str]
```

- server lifespan 启动时：`manager.start_all_enabled()`——遍历 `im_connectors` 中 `enabled=1` 的平台逐个 start。
- 运行时启停：`/admin/im/connectors/{p}/enable` 置 `enabled=1` 并 `manager.start(p)`；`/disable` 置 `enabled=0` 并 `manager.stop(p)`。
- adapter 任务异常退出：manager 捕获并置 `status=error` + `last_error`，不拖垮其他平台；是否自动重启由 adapter 自身的重连逻辑负责（既有 `im-gateway` 的 reconnect 契约不变），manager 只反映状态。

manager 持有的运行态（`Task` 集合）是**进程内**的；多机集群下每个实例各自管理本机连接器（与 `platform.md` 待决的集群项一致，本 change 不解决跨机协调）。

## 状态上报

adapter 在关键时刻调用 `im_connector_store.report_status(platform, status, error=None)` 与 `heartbeat(platform)`：

- `status ∈ {stopped, connecting, connected, disconnected, error, unconfigured}`
- `connected` 时定期 `heartbeat` 刷新 `last_heartbeat_at`；健康仪表盘据此判断"虽标 connected 但心跳过期 = 疑似假死"。
- 状态只写 DB（`im_connectors` 行），读侧（健康仪表盘 / `/admin/im`）按 DB 渲染，避免读运行态内存。

`unconfigured`：平台已登记但 config 无有效令牌（如 whatsapp 占位）——manager 不会 start，UI 显示"未配置"。

## channel 白名单强制点与 opt-in

- 强制点在 `normalizer.route` 最前：取 `(msg.platform, msg.channel_id)`，调用 `im_channel_allowlist.is_allowed(platform, channel_id, workspace_id)`。
- **per-platform opt-in**：`im_connectors.allowlist_enforced`（默认 0）。为 0 时 `is_allowed` 恒真（兼容当前 MVP，无白名单也能用）；为 1 时仅当存在匹配的 `allowed=1` 条目才放行，否则 adapter 回拒绝提示、消息不进管线。
- 粒度：`scope_type ∈ {channel, workspace}`。workspace 级允许"整个 Slack workspace / Telegram 群组放行"，channel 级精确到单 channel。匹配时 channel 级与 workspace 级任一命中即放行。
- 校验结果（拒绝）写一条审计/日志，便于排查"为什么这个 channel 不通"。

## 配置解析与脱敏

`im_connector_config.resolve(platform) -> dict`：

1. 读 `im_connectors.config`（JSON），非空则用之；
2. 否则回退 `config.Settings`（`.env`）对应字段（slack_bot_token / slack_app_token / telegram_bot_token）。

- adapter 只经 `resolve()` 拿原始令牌；
- API / CLI 经 `resolve_masked(platform)`，令牌字段只保留尾 4 位（如 `xoxb-****abcd`）；
- `seed-connectors`：一次性把 `.env` 现有令牌写入对应 `im_connectors.config`、有令牌则 `enabled=1`；幂等（已存在 config 的平台跳过，除非 `--force`）。

令牌明文落本机 SQLite——与 `.env` 文件同等信任边界，符合"数据不出内网"；不引入云 KMS。是否做本地加密存储留为后续可选项，不在本 change。

## WhatsApp 占位

`im_connectors` 预置一行 `platform="whatsapp"`、`status="unconfigured"`、`enabled=0`、无 adapter 实现。框架（注册表 / config / 白名单 / API / CLI）对它一视同仁；adapter 缺失时 `manager.start("whatsapp")` 直接置 `unconfigured` 并跳过，不报错。后续接入只需补一个 adapter + 在 manager 注册工厂。

## 测试隔离（遵循 CLAUDE.md）

- `im_connector_store` / `im_channel_allowlist` 复用 `user_store._conn` 与可 monkeypatch 的 `DB_PATH`；测试 `monkeypatch DB_PATH` 到 `tmp_path`。
- `im_connector_manager` 测试用假 adapter 工厂（注入），不起真实 socket；验证 start/stop/reload 的状态流转与任务取消。
- adapter 状态上报测试：mock `report_status` / `heartbeat`，断言在连接 / 断线 / 错误时被正确调用，不连真实 Slack / Telegram。
- 路由白名单测试：构造 `NormalizedMessage`，monkeypatch allowlist 表，断言 enforced 开/关、命中/未命中、channel/workspace 粒度的放行与拒绝。

## 认证守卫依赖

`/admin/im/*` 复用 `agent-admin-api` 的 `users.is_admin` 守卫。实施顺序上若该 change 未先合入，tasks 0.x 会先确认 / 补齐 admin 守卫，再挂载本 router。
