## Why

`generate` 类定时任务的语义是「到点产出通知正文,**由调度器投递**该回复」(fire 时注入 delivery statement,最终回复被广播到 deliver/origin 目标)。但 generate 的 agent run 当前仍**暴露外发工具**(`send_im_message`/`send_file`),于是模型可能在 run 内**自己再发一遍**(尤其 prompt 写了「发送给X」时),叠加调度器的广播 → **同一内容双投递**(线上金价任务已观测:模型自发 DM + 调度器广播到创建频道)。

`action` 类则相反:其语义就是「agent 用自身工具行动」,调度器**不**广播——外发工具必须保留。

## What Changes

- `runtime/loop.run()` 新增参数 `suppress_outbound_tools: bool = False`:为真时,从本次 run 的工具 schema 中**移除外发投递工具**(`send_im_message`、`send_file`)。
- `cron_scheduler._fire` 在调 `_agent_run` 时按类型透传:`generate` → `suppress_outbound_tools=True`(投递交调度器,模型只产出正文);`action` → `False`(保留外发工具,agent 自己投递)。`notify` 不跑 agent,无关。
- 连接器快照(AAA-8039)对 `action` 仍照常注入;本变更只收口 `generate` 的工具面,不动连接器线程化。
- 范围:仅收口两个**内置**外发工具;MCP 写工具(如 slack `conversations_add_message`)不在本变更内(部署相关、且常已被 server 端 policy 关闭)。

## Capabilities

### Modified Capabilities
- `scheduled-task-delivery`:新增「generate fire 不暴露外发工具,投递仅由调度器完成;action fire 保留外发工具」。
- `cron-scheduled-tasks`:把「Fired run can deliver via IM tools」场景明确为 **action** 类(generate 不再暴露外发工具)。

## Impact

- **owning package**:`runtime/`(`loop.run` schema 过滤 + 新参数)、`cron_scheduler`(generate/action 透传)。
- **public API surface**:`run()` 新增可选参数 `suppress_outbound_tools`(默认 False,向后兼容);`_agent_run` 内部新增同义参数。
- **owned tables / config / migration**:无。
- **cross-module dependencies**:沿用 `cron_scheduler`→`runtime.loop` 既有依赖;零 `fleetent.platform.*` import。
- **async lifecycle**:无新长生命周期资源。
