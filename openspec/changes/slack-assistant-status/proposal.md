## Why

Slack 适配器的 per-tool 状态指示器实际**没有渲染到用户看到的 Assistant 面板**:用户看到的是 Slack 默认的本地化 loading 轮播(「处理中…」「审核结果中…」),而非 fleetent 设置的「📅 正在查询日历…」等文案。运行时插桩已证实 fleetent 的 `assistant_threads_setStatus` 调用全部成功且文案正确,但落在了**错误的 thread** 上——根因是 fleetent 未遵循 Slack Assistant 协议:没有监听 `assistant_thread_started` 拿到 assistant 线程真正的 `thread_ts`,而是用消息自身的 `event.get("ts")`。

此外,多工具一轮并行执行时,进度只反映其中一个工具,无法体现真实执行链路。

## What Changes

- **Slack 适配器改用 slack-bolt 的 `Assistant` 容器/中间件**(已有依赖 `slack-bolt>=1.28`):监听 `assistant_thread_started`,捕获并使用 assistant 线程真实的 `channel_id` + `thread_ts`,使 `setStatus` / 最终回复 / 图片上传都绑定到**正确的 thread**,状态指示器真正渲染到 Assistant 面板。
- **保留 channel `app_mention` 路径**:Assistant 容器仅覆盖 DM/assistant 面板场景;频道 @mention 仍按现有方式处理。
- **多工具进度表示修正**:一轮包含多个并行工具调用时,进度展示 SHALL 体现该轮**全部**在途工具(聚合/列表),而非只显示最后一个;进度文案反映实际执行而非规划顺序。
- **降级行为不变**:未启用 Agents & Assistants 的 App 仍平滑降级为纯 `say()` 回复。
- **Telegram 无专属改动**:仅随共享的进度发出逻辑调整,回归确认其 typing 指示不退化。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `im-progress-feedback`: Slack 进度展示从「裸调 `assistant_threads_setStatus` + 消息 ts」改为「遵循 Assistant 协议、绑定 assistant 线程真实 `thread_ts`」;并将多工具一轮的进度表示从「只反映最后一个工具」改为「体现该轮全部在途工具」。

## Impact

- **代码**:
  - `src/fleetent/im_gateway/slack.py`:事件处理层重构为基于 `Assistant` 容器,捕获 assistant 线程标识。
  - `src/fleetent/runtime/loop.py`:进度事件的发出位置/聚合方式调整(配合多工具进度表示)。
- **依赖**:无新增;`slack-bolt>=1.28` 已满足 `Assistant` 类要求。
- **测试**:`tests/unit` 新增 Slack Assistant 协议单测(mock client:验证捕获 thread_ts、setStatus 绑定正确 thread、降级路径)与 loop 进度时机/聚合单测;Telegram 进度回归。
- **架构约束**:改动全部在 agent runtime(`im_gateway/`、`runtime/`),不 `import fleetent.platform.*`、不写 platform 表;agent 必须仍能脱离 platform 独立运行。
