## Why

`fleetent agent run <id>`（standalone agent runtime）启动 Slack/Telegram 连接器时崩在
`no such table: users`，连接器静默 `error`，agent 收不到也回不了 IM 消息。

崩点在 supervisor 启动时**急切解析 owner_id**：`SlackSupervisor` / `TelegramSupervisor` 的
`owner_id_provider` 默认是 `user_store.admin_owner_id`，后者执行
`SELECT … FROM users WHERE role='built_in_admin'`——读 **platform 管理表 `users`**。standalone 进程的
DB 没有 `users` 表（`users` 由 Alembic 建于管理库、seed 只在 platform 路径），于是 `_run()` 第一行
`self._owner_id_provider()` 就抛错。这违反 AGENTS.md 解耦验证基线：「agent 必须能在『无 platform、
platform 的 DB 表不存在』环境下完成 `fleetent agent run`」；`im_gateway` 是 agent 运行时模块，
MUST NOT 触碰 platform 数据。

进一步追查发现 **owner_id 在整条 agent IM 链路里已无实际用途**：

- 它从 supervisor 线程化经 `slack/telegram.run → create_app → NormalizedMessage.owner_id`，
  **唯一**消费点是 `normalizer.py` 把它拼成 session_id 前缀（`f"{owner_id}:{session_id}"`，372/446 两处）。
- 该前缀的设计意图（代码注释）是「同一 platform/channel 在两个 owner 下不串会话」的 multi-owner 命名空间。
  但此命名空间**已无任何活的生产者**：platform 已不在 boot 启动 IM 连接器（`server.py` 注释），
  `server.py:87` 的 `ConnectorManager(factories={})` 是空工厂，owner-level adapter 全撤；全仓**唯一**构造
  `NormalizedMessage` 的就是 `im_gateway/slack.py`（3 处）+ `telegram.py`（1 处），均为 standalone 单 owner
  路径，owner_id 恒为同一值。前缀是 owner-level 连接器时代的历史化石。
- 访问控制、身份、审批、记忆全部基于 `msg.user_id`（IM 身份），不依赖 owner_id。

因此「塞个安全哨兵默认值」只是掩盖——正解是**把 owner_id 从 agent IM 连接器链路整条移除**，并去掉
session_id 的 owner 前缀。这同时：(1) 去掉前缀（已确认无活的 multi-owner 依赖）；(2) 从根上消除崩溃
（supervisor 不再解析 owner_id、不再调 `admin_owner_id`）；(3) 删除无用的线程化与 `im_gateway → user_store`
反向 import。

## What Changes

- `im_gateway/slack_supervisor.py` / `telegram_supervisor.py`：移除 `owner_id_provider` 构造参数与
  `_owner_id_provider`；`Runner` 签名由 `(agent_name, owner_id, config)` 改为 `(agent_name, config)`，
  `_run()` 改 `await runner(agent_name, config)`；删除仅为 `admin_owner_id` 而存在的 `user_store` import。
- `im_gateway/slack.py` / `telegram.py`：`run()` / `create_app()` 去掉 `owner_id` 参数；构造
  `NormalizedMessage` 时去掉 `owner_id=...`。
- `im_gateway/normalizer.py`：`NormalizedMessage` 删除 `owner_id` 字段；session_id 推导去掉 owner 前缀
  （372/446 改为直接用 `msg.session_id`）。
- 不动 `user_store.admin_owner_id` 本身（platform 域仍可用）；不动 platform `im_gateway_management`
  的 owner_id 概念（`im_connectors`/`im_channel_allowlist`/`im_users` 按 `(owner_id, platform)` 建键——
  与 agent IM 链路 owner_id 无关，完全独立）。
- 测试同步：删除/改写 `test_im_adapter_owner.py`（断言已移除的 owner 线程化），更新构造
  `NormalizedMessage(owner_id=...)` 或注入 3 参 runner 的相关测试。

## Capabilities

### New Capabilities
<!-- 无新增 capability；移除既有 owner_id 线程化 + 落实解耦基线 -->

### Modified Capabilities

- `per-agent-slack-connector`：连接器不再线程化 owner_id、不再解析任何 platform 表；session_id 推导
  不含 owner 前缀；连接器在「无 `users` 表」环境下正常启动。
- `per-agent-telegram-connector`：同款（镜像 Slack）。

## Impact

- **owning package**：`im_gateway`（owner：`per-agent-slack-connector` / `per-agent-telegram-connector`）。
- **public API surface**：`SlackSupervisor` / `TelegramSupervisor` 构造去掉 `owner_id_provider` 参数；
  `Runner` 类型与 `slack/telegram.run`、`create_app` 去掉 `owner_id` 形参；`NormalizedMessage` 去掉
  `owner_id` 字段。均为 im_gateway 内部协作面，无跨包公共 API 依赖该形参/字段（platform 不调）。
- **owned tables**：无变化（`users` 仍属 platform；本 change 只是不再从 agent 运行时读它）。
- **config namespace**：无。
- **cross-module dependencies**：**消除** `im_gateway → user_store.admin_owner_id → 管理库 users` 的
  运行时反向读取，并删除 `im_gateway/{slack,telegram}_supervisor` 对 `user_store` 的 import。方向回归单向。
- **migration / shim plan**：无（无表/配置/路径常量变更）。session_id 格式由 `owner:sid` 变为 `sid`：
  按项目「上线前不迁移数据」约定，旧带前缀的 IM 会话文件作孤儿、由部署方按需清理（standalone Slack
  此前一直崩、无有效历史会话）。
- **验证基线**：「无 platform、无 `users` 表」环境下 `fleetent agent run` 启动 Slack/Telegram 连接器
  不再报 `no such table: users`；guardrail 守住 `im_gateway` 运行时零 platform 数据依赖。
