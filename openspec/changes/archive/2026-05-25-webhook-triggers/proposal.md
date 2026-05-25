## Why

fleetent 目前只能被动响应 IM 消息，无法被外部系统主动触发。CI 构建完成、监控告警触发、GitHub PR 合并等高频工作流事件，都需要一个 Webhook 入口才能调用 agent 自动处理。这是把 agent 从"聊天工具"变成"自动化节点"的关键缺口。

## What Changes

- `server.py` 新增 `POST /webhook/{source_id}` 端点，接收外部系统 POST 请求
- 新增 `webhook_router.py`：加载 `config/webhooks.yaml`，按 `source_id` 查找配置，验证签名（HMAC-SHA256），从 payload 提取消息文本，构造 `NormalizedMessage`，异步派发给现有 pipeline
- `config/webhooks.yaml`（示例文件）：定义 webhook source 列表，每个 source 含 `id`、可选 `secret`、目标 `user_id`、可选 `agent_name`、可选 `message_template`
- HTTP 响应即时返回 202 Accepted，agent run 在后台异步执行（fire-and-forget）
- `reply_func` 为 no-op：webhook 触发的 agent 运行结果写入 eval trace，不反向推送（第一版）

## Capabilities

### New Capabilities

- `webhook-triggers`：外部系统通过 HTTP POST 触发 agent run，支持 HMAC-SHA256 签名验证和 payload 文本模板提取

### Modified Capabilities

无

## Impact

- **代码**：`server.py`（新路由）；新增 `webhook_router.py`
- **配置**：新增 `config/webhooks.yaml`（示例，不强制存在）
- **依赖**：无新依赖（HMAC 在标准库 `hmac` 中）
- **破坏性**：无，新增端点不影响现有路由
