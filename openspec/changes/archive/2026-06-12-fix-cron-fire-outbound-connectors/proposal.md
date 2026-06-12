## Why

定时任务（Jira **AAA-8039**「定时任务不可用」）触发后无法把消息投递到 Slack。2026-06-11
dev-intern 实测：任务到点触发、agent 跑起来了，但 agent 在 run 内调用发送工具时报「无可用
Slack 连接器」，最终用户收到的是一段故障说明而非任务内容。

根因（代码级已钉死）：`cron_scheduler._fire` 在 fire 时**已正确拿到** fire 时连接器快照
（`connectors = self._connectors_resolver()`，由 `agent_app` 注入 `connector_registry.snapshot`），
并成功用于 fire 后的 `_deliver`——所以 agent 的故障说明本身能投递出去。但 `_fire` 调用
`_agent_run(...)` 进而 `agent_loop.run(...)` 时**没有把 `outbound_connectors` 传进去**
（`cron_scheduler.py:85`）。于是 fired run 内部的 `send_im_message` 等出站工具
（`tool_context.outbound_connectors`）拿到空字典 → 任何「到点主动发消息/私信/通知」的任务在
run 内发不出去。对比：交互式 @ 消息因 normalizer 经入站上下文传了 `outbound_connectors`，
所以正常（频道通知 8052 实测通过）——只有「无入站上下文、自己醒来干活」的定时场景缺这一环。

`agent_loop.run` 早已支持 `outbound_connectors` 形参（`runtime/loop.py:1533`），缺的只是
cron 这条调用链没有把已在手的快照线程化进去。

## What Changes

- `cron_scheduler._agent_run` 新增 `connectors: dict[str, Any] | None` 形参，转发为
  `agent_loop.run(..., outbound_connectors=connectors or {})`。
- `cron_scheduler._fire` 在调用 `_agent_run` 时把它已持有的 `connectors`（fire 时快照）传下去。
- 两条触发路径（APScheduler `_task_fire` 与 `run_now`）都已在 fire 时现取快照后调用 `_fire`，
  故自动受益，无需各自改动。

不改投递（`_deliver`）逻辑、不改 `schedule_kind`/调度/missed-run 语义、不动 `connector_registry`。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `cron-scheduled-tasks`：明确「触发的 agent run 必须携带 fire 时解析的 `outbound_connectors`
  快照」，使定时任务内的出站工具可达 IM 连接器。

## Impact

- **owning package**：agent 运行时调度域（平铺 `cron_scheduler.py`）。capability owner：`cron-scheduled-tasks`。
- **public API surface**：`cron_scheduler._agent_run` 内部 helper 增形参（非跨包公共 API）；
  `agent_loop.run` 签名不变（用既有形参）。
- **owned tables**：无。**config namespace**：无。
- **cross-module dependencies**：沿用 `cron_scheduler → runtime.loop`、`→ im_gateway.connector_registry`
  （fire 时快照，已有），零 platform 触碰（守住 cron 的 agent-owned 无 platform 依赖契约）。
- **migration / shim plan**：无。
- **验证基线**：无 platform 环境下，声明 `connectors.slack` 的 agent 创建「N 秒后向频道发消息」
  的一次性任务，到点频道**收到该消息内容本身**（而非「连接器未运行」故障说明）。Jira AAA-8039。
