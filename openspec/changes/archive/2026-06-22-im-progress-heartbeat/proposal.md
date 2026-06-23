## Why

IM 进度指示(Slack `assistant_threads.setStatus`、Telegram `send_chat_action("typing")`)目前只在**工具调用边界**刷新一次(`run()` 每轮执行工具前调一次 `progress_func`)。在三类长静默区间——长 LLM 调用、单个长工具(如 run_code)、整个 sub_agent 执行——**没有任何事件刷新指示**:Slack 状态过期消失,Telegram typing 约 5 秒后自动消失。结果用户**分不清 agent 还在跑还是服务卡死**。Telegram 尤其严重,因为 typing 本就必须周期性重发。

## What Changes

- **新增时间驱动心跳**:`runtime/loop._run_inner` 在顶层 run(`not is_sub_agent` 且 `progress_func is not None`)期间启动一个心跳 task,每约 4 秒(压在 Telegram 5s typing 窗口内)调用 `progress_func({"type": "heartbeat", "elapsed_s": N})`。心跳 task 在同一协程内 `create` + `finally` 中 `cancel()` + `suppress(CancelledError)`(owner-task 契约),并**舱壁化**——心跳异常只记日志,绝不影响 run、不改退出码。**sub_agent 不启动自己的心跳**(父级心跳已覆盖其墙钟,且 sub_agent 的 `progress_func` 为 None)。
- **Slack 适配器加 `heartbeat` 分支**:记住上次**非心跳**的工具状态文案,心跳到来时重发「`<上次文案> · 已 Ns`」,既保活 setStatus 又显示耗时(活性提示);心跳与工具事件不互相清掉对方的文案。
- **Telegram 适配器**:`progress_func` 对任意 progress 事件已发 typing,心跳事件自然 re-arm 那 5 秒窗口——确认其对 `heartbeat` 事件同样发 typing(必要时小调,不新增分支逻辑)。
- 心跳间隔为**可注入的模块级常量**(约 4s);**always-on,无配置开关**(核心 UX)。
- 范围限「保活 + 活性提示(耗时)」;**不做** sub_agent 内部粒度进度透传。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `im-progress-feedback`: 在既有「工具边界一次性 progress 事件 + Slack Assistant 状态 + Telegram typing」之上,新增**时间驱动心跳事件**(`{"type":"heartbeat","elapsed_s":N}`),在长 LLM / 长工具 / sub_agent 等静默区间周期性保活 IM 指示;Slack 据此重发「上次文案 + 耗时」,Telegram 据此 re-arm typing;心跳 task 遵守 owner-task 契约且舱壁化。

## Impact

- **owning package**:`runtime/`(`loop.py` 心跳 task + 发射)、`im_gateway/`(`slack.py` heartbeat 分支;`telegram.py` 确认/小调)。
- **public API surface**:`progress_func` 事件契约新增事件类型 `heartbeat`(携带 `type` + `elapsed_s`,无敏感信息);`run()`/`_run_inner()` 签名不变(心跳是内部行为)。
- **owned tables**:无。
- **config namespace**:无(心跳间隔为模块级可注入常量,无 agent.yaml 字段)。
- **cross-module dependencies**:沿用既有 `progress_func` 契约;`runtime`/`im_gateway` 均为 agent 运行时模块,**零 `fleetent.platform.*` import**;零新第三方依赖。
- **async lifecycle**:心跳为长生命周期 task,MUST 同协程 `create`+`cancel`、`finally` 保证取消、逐步舱壁化(owner-task 契约,2026-06-11 事故同类雷区)。
- **migration / shim plan**:无表、无迁移、无模块迁移。
