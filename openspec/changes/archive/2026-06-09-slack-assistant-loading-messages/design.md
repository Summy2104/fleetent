## Context

上一个 change（slack-assistant-status）让 Slack 底部状态栏正确显示 per-tool emoji 状态。但 Slack Assistant UX 有两层指示：`status`（底部状态栏）与 `loading_messages`（消息区定时轮播的占位）。`set_status(status, loading_messages=None)` 中未传 `loading_messages` 时，Slack 用内置本地化默认（「整体梳理中…」等）填充消息区轮播。

## Goals / Non-Goals

**Goals:**
- 消息区轮播展示 fleetent 的工具文案，而非 Slack 内置默认。
- 与底部状态栏内容保持一致（同一批次的工具文案）。

**Non-Goals:**
- 不改底部状态栏逻辑（已正确）。
- 不追求轮播与工具实际完成严格同步——`loading_messages` 由 Slack 按其计时器轮播，本质是装饰；准确的执行指示由底部 `status` 承担。
- 不动 channel / 非-assistant fallback（无消息区轮播）。

## Decisions

### D1: loading_messages 镜像当前批次工具文案
`set_status` 同时传 `loading_messages=[逐工具可读文案]`（复用 `_tool_status_text`）。批次变化时随 `set_status` 一起更新；初始阶段传 `["🤔 思考中..."]`。
- *备选*：单条静态文案（消除轮播）。否决：用户希望消息区反映工具链路，镜像更贴合（已选）。

### D2: 仅 Assistant 路径
`loading_messages` 经 slack-bolt 的 `set_status` 工具传递,仅 `_route_assistant_message` 用到。fallback（`_make_status_funcs` 裸调 `assistant_threads_setStatus`）服务非-assistant 场景,无消息区轮播,不改。

## Risks / Trade-offs

- [loading_messages 轮播由 Slack 计时,与真实完成解耦] → 可接受：底部 `status` 已是准确的逐批指示，loading_messages 仅消息区装饰。
- [文案过多] → 复用既有 `_aggregate`/`_tool_status_text`,列表长度等于本批工具数（通常 1–3），不设额外截断。
