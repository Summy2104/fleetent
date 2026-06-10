## Why

审批交互目前只有文本命令（回复 `approve <id>`），对 Slack 用户不友好且易输错；`permission-gate` 主 spec 的 Async approval wait 场景本就写着「user clicks "Allow" in the IM approval message」——按钮从设计起就是预期形态，实现缺失。Slack 适配器现状完全没有 Block Kit / 交互事件支持（全部 `say(text)` 纯文本），这也是 Jira AAA-8051「slack 按钮渲染失败」的基础设施根因。审批分层批次 Change 2/3。

## What Changes

- **审批提示 Block Kit 化（Slack）**：requester 会话内提示与外呼审批人 DM 均升级为「描述 + [✅ 批准] [❌ 拒绝] [✅ 始终允许] 按钮」的 Block Kit 消息；按钮 value 携带 approval_id
- **Socket Mode 点击处理**：`slack.py` 注册 `block_actions` 处理器——点击者身份取自 Slack 事件（`body.user.id`，比文本命令更可靠的身份来源），经 Change 1 的授权校验调 `gate.resolve()`；成功后 `chat.update` 把原消息改写为结果态并移除按钮（防重复点击）；非授权点击回临时提示
- **平台无关降级**：gate 经"能力探测"传递结构化审批动作——`reply_func` / `send_to` 支持 blocks 的平台（Slack）渲染按钮，不支持的（Telegram/TUI）维持纯文本；文本命令 `approve/reject <id>` 全平台保留
- Block Kit 渲染助手放 `outbound.py`（它已承载 Slack API 细节），governance 不感知 Block Kit 结构

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `im-gateway`: 新增 Slack 审批交互 requirement（按钮渲染、block_actions 处理、点击者身份、结果态更新、文本命令降级保留）
- `permission-gate`: 新增「审批提示在支持的平台携带交互动作」requirement（平台无关表述，文本命令为全平台兜底）

## Impact

- **代码**：`outbound.py`（approval blocks 渲染助手 + `send_to` 可选 blocks 参数）、`governance/permission_gate.py`（提示发送时附带 blocks，TypeError 降级纯文本）、`im_gateway/slack.py`（reply_func 接受可选 blocks、注册 action 处理器）
- **部署要求**：Slack App 需开启 Interactivity（Socket Mode 下事件走现有连接，无需公网回调）——写入决策文档
- **不改**：Telegram/TUI 行为、文本命令格式、gate 授权与超时语义
