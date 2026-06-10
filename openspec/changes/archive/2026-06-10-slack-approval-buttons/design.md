## Context

现状（已核实）：

- `slack.py` 全部回复走 `say(text=...)`，零 Block Kit；无任何 `app.action` / `block_actions` 处理器
- 审批提示两条出口：requester 路由经 `reply_func(text)`（Change 1）；外呼经 `outbound.send_to(platform, connector, target, text)`
- `gate.resolve(approval_id, decision, approver_user_id, always)` 已有授权校验（Change 1），点击者身份过同一校验即可
- Socket Mode 下 `block_actions` 交互事件走现有连接（slack-bolt `app.action` 注册即收），无需公网 URL

## Goals / Non-Goals

**Goals:**
- Slack 上的审批提示（会话内 + 外呼 DM）渲染为带三按钮的 Block Kit 消息
- 点击 → 取真实点击者 id → gate.resolve →（成功）chat.update 写结果态移除按钮 /（非授权）临时提示
- 不支持 blocks 的通道（Telegram/TUI）无感降级纯文本；文本命令全平台保留

**Non-Goals:**
- Telegram inline keyboard（后续可加，本切片不做）
- agent 普通回复的 Block Kit 化（AAA-8051 的完整诉求属后续；本切片只为审批消息立基础设施）
- 审批超时后主动撤回/置灰按钮消息（超时点击会因 approval 不存在而提示过期，足够）

## Decisions

**D1 Block Kit 渲染助手放 `outbound.py`，governance 不感知 Slack 结构。**
`outbound.approval_prompt_blocks(approval_id, tool_name, risk_level)` 返回 Slack blocks；gate 只把它当不透明 payload 传递。outbound 已承载 Slack API 细节（`chat_postMessage` 等），是平台渲染知识的既有归属地。
- 备选：放 `im_gateway/slack.py`。否决——gate import slack.py 会把 governance 拽进适配器层；outbound 是 gate 已依赖的底座。

**D2 能力探测降级：`reply_func(text, blocks=...)` 抛 TypeError → 纯文本重发。**
Slack 的 reply_func 增加可选 `blocks` 关键字；Telegram/TUI 的 reply_func 不改，gate 调用时 `try: reply_func(text, blocks=...) except TypeError: reply_func(text)`。
- 备选：给 NormalizedMessage 加 capability flag。否决——TypeError 探测零侵入，旧适配器/测试 mock 全部自然兼容；AsyncMock 接受任意 kwargs 也不会误降级（直接成功）。

**D3 三个独立 action_id：`approval_approve` / `approval_reject` / `approval_approve_always`，value=approval_id。**
decision 由 action_id 决定、id 由 value 携带——单处理器按前缀注册（`re.compile("^approval_")`），分发清晰。

**D4 点击结果反馈：成功 → `chat.update` 原消息为结果态文本（含决策人）并清空 blocks；失败（非授权/过期）→ `chat_postEphemeral` 仅点击者可见的提示。**
chat.update 防重复点击：第二人点击时按钮已不在。竞态窗口内的重复点击由 gate 幂等性兜底（Event 已 set，resolve 返回 False → ephemeral 提示）。

**D5 `send_to` 增加可选 `blocks` 参数，仅 Slack 路径消费。**
`_slack_send_dm` / `_slack_send_channel` 透传 `blocks`（`text` 同时保留作通知 fallback）；Telegram 路径忽略。签名向后兼容（默认 None）。

## Risks / Trade-offs

- [Slack App 未开 Interactivity] 按钮显示但点击无响应 → 文本命令仍可用（提示文案保留 `approve <id>` 指引作为按钮的并行说明）；部署要求写入决策文档
- [chat.update 失败]（权限/消息过旧）→ suppress + 日志，决策本身已生效（gate 先 resolve 后 update）
- [测试中 AsyncMock reply_func 不会触发降级] 行为是"直接接受 blocks kwarg"——与 Slack 真实行为一致，无碍
- [按钮与文本命令双轨] 同一 approval 可被任一方式决策——gate 幂等，先到先定

## Migration Plan

纯增量：未点按钮时一切同 Change 1 后状态；Telegram/TUI 零变化。无 schema/配置变更。

## Open Questions

（无）
