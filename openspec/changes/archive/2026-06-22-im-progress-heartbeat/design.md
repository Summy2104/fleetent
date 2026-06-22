## Context

进度反馈链(`im-progress-feedback`):`NormalizedMessage.progress_func` 经 `run()`→`_run_inner()` 透传;`_run_inner` 在每轮**待执行工具批次实际执行前**调一次 `progress_func({"type":"tool_call","names":[...]})`(带 `not is_sub_agent` 守卫)。

- Slack(`im_gateway/slack.py`):`progress_func` → `assistant_threads.setStatus(status=_status_text_for_event(evt), loading_messages=_loading_messages_for_event(evt))`;最终回复时 `set_status("")` 清除。
- Telegram(`im_gateway/telegram.py`):`progress_func` → `send_chat_action(action="typing")`(对事件内容不敏感,任意事件都发)。

**缺口**:两端指示都是**事件驱动**,只在工具边界刷新。长 LLM 调用 / 单个长工具 / 整个 sub_agent 执行期间无事件 → Slack 状态过期、Telegram typing ~5s 自动消失。

约束:`runtime`/`im_gateway` MUST NOT import platform;长生命周期 async 资源须遵守 **owner-task 契约**(同 task create/cancel、舱壁化、优雅退出 0);TDD Hard Gate。

## Goals / Non-Goals

**Goals:**
- 长 LLM / 长工具 / sub_agent 期间,Slack 状态与 Telegram typing **持续保活**,不消失。
- Slack 额外显示**活性提示(已耗时)**,让状态可见地变化,证明在跑。
- 时间驱动、双端通吃、零新依赖、零 platform 依赖、心跳故障不影响 run。

**Non-Goals:**
- 不做 sub_agent 内部粒度进度透传(不改 sub_agent 的 progress 行为)。
- 不加配置开关(always-on)。
- 不改 `progress_func` 既有 `tool_call` 事件语义,不改 run()/_run_inner() 签名。
- 不引入文件 watcher 之外的后台机制以外的东西;不动 TUI/HTTP 流式的既有进度。

## Decisions

### D1:心跳放在 core loop(`_run_inner`),时间驱动
在 `_run_inner` 顶层 run 体内启动一个心跳协程任务;它 `while True: await sleep(interval); await progress_func({"type":"heartbeat","elapsed_s":int(now-start)})`。因为是**时间驱动**而非事件驱动,它天然覆盖长 LLM 调用、单个长工具、整个 sub_agent 执行——这些正是事件驱动方案的盲区。经现有 `progress_func` 契约,一个心跳同时驱动 Slack 与 Telegram。
- 备选:表现层(slack.py)各自起心跳 —— 否决:Telegram 也需要(typing 5s 必重发),core-loop 一处通吃;且表现层拿不到统一的「run 在途」时机。

### D2:仅顶层 run 起心跳,sub_agent 不起
守卫 `not is_sub_agent and progress_func is not None`。sub_agent 的 `progress_func` 为 None(既有契约),且父级心跳的墙钟已覆盖 sub_agent 执行期。父心跳在 sub_agent 执行期间持续发 `heartbeat`(从父视角 sub_agent 只是一个长工具),保活不断。

### D3:owner-task 生命周期 + 舱壁化
心跳 task 在 `_run_inner` 内 `asyncio.create_task` 创建,用 `try / finally` 保证 run 结束(正常或异常)时 `cancel()` 并 `await` 吞掉 `CancelledError`——**同一协程内 create+cancel**,符合 anyio/owner-task 契约。心跳循环体整体 `try/except`:`progress_func` 抛错只 `logger.warning` 不外抛(沿用既有 progress 容错),`sleep`/cancel 正常传播。心跳绝不改变 run 的返回值或退出码。
- 实现要点:把心跳收口成一个独立小函数 `_progress_heartbeat(progress_func, start, interval)`,便于单测(直接驱动它、断言按 interval 发 heartbeat 事件且吞异常)。

### D4:间隔 ~4s,可注入模块级常量
`_HEARTBEAT_INTERVAL_S = 4.0`(模块级,测试可 monkeypatch 调小)。选 4s 的依据:Telegram typing 窗口约 5s,4s < 5s 保证不断档;Slack `setStatus` 每 4s = 15 次/分,远低于 Web API 速率上限。always-on,无 agent.yaml 开关(YAGNI + 核心 UX)。

### D5:Slack heartbeat 分支——保活 + 耗时,不互相清文案
Slack 的 progress 处理引入一个**每会话的「上次工具状态文案」记忆**(闭包内可变 holder)。`tool_call` 事件:更新 holder 为该批工具文案并 setStatus。`heartbeat` 事件:重发「`<holder 文案> · 已 {elapsed_s}s`」(holder 初始为「🤔 思考中...」)。两类事件都只调 setStatus,不会互相清成空。`loading_messages` 心跳时复用 holder 对应的逐工具文案(或思考中)。
- 备选:心跳直接覆盖成固定「思考中…」 —— 否决:会抹掉当前工具上下文,信息倒退。

### D6:Telegram 无需新分支
`telegram.py` 的 `progress_func` 对**任意**事件 `send_chat_action("typing")`,心跳事件天然 re-arm。本设计仅**确认**该行为(加一条针对 heartbeat 的测试),不新增分支。

## Risks / Trade-offs

- **心跳 task 泄漏/跨 task 取消**(owner-task 雷区) → D3:同协程 create + finally cancel + suppress;独立小函数便于测试取消路径。
- **Slack setStatus 速率限制** → 4s 间隔(15/min)远低于上限;且失败被 progress 容错吞掉。
- **心跳与 tool_call 事件竞争 setStatus** → 都走 setStatus、由 holder 统一文案,顺序到达即可,不互相清空;Slack 端单线程事件循环,无需额外锁。
- **sub_agent 期间 holder 停在「sub_agent」文案** → 可接受(活性提示=「调用 sub_agent · 已 Ns」),符合「不做粒度透传」的范围。
- **心跳事件被误当工具事件** → 新事件类型 `heartbeat` 与 `tool_call` 区分;Slack 按 type 分支,Telegram 不区分(都发 typing)。

## Migration Plan

- 纯增量:loop 内新增心跳 task + 一个事件类型 + Slack 一个分支。无 DB、无 platform、无迁移、无签名变更。
- 默认即生效(always-on)。回滚 = 移除心跳 task 启动与 Slack heartbeat 分支。

## Open Questions

无(层级=core loop、范围=保活+耗时、间隔≈4s、无开关、sub_agent 不起独立心跳——均在 brainstorm 敲定)。
