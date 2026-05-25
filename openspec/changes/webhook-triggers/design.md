## Context

`server.py` 是 FastAPI 应用，已有 `/chat`（SSE 流式）、`/health`、`/approvals` 等路由。`normalizer.route()` 是标准 IM 消息派发入口，接受 `NormalizedMessage` 并处理 allowlist 检查、agent 解析、session 管理、agent_loop 调用。Webhook 事件本质上是"外部系统发来的消息"，可以复用这条 pipeline。`config/` 目录已有 `mcp.yaml`、`settings.yaml`，模式统一：YAML 文件 + 服务启动时加载。

## Goals / Non-Goals

**Goals:**
- `POST /webhook/{source_id}` 接收任意 JSON payload
- HMAC-SHA256 签名验证（可选，secret 不配置时跳过验签，适合内网）
- `message_template` 从 payload 提取消息文本（Python str.format_map 风格）
- 即时 202 响应，agent run 在后台 asyncio task 执行
- 复用现有 `normalizer.route()` pipeline（session 管理、agent 解析、allowlist 均已处理）

**Non-Goals:**
- 结果回推（不反向调用外部系统 callback URL，第一版先记录到 trace）
- 支持非 JSON payload（如 form-urlencoded）
- 多签名算法（只做 HMAC-SHA256，覆盖 GitHub/GitLab/大部分 CI 系统）
- Webhook 管理 API（source 配置只通过 YAML，不提供 CRUD endpoint）

## Decisions

### 1. 新建 `webhook_router.py` 而非直接写在 `server.py`

`server.py` 已经有明确职责（FastAPI app + auth + lifespan），webhook 逻辑（配置加载、验签、payload 解析）单独一个模块更清晰，也方便测试（不需要启动完整 FastAPI app）。在 `server.py` 中用 `app.include_router()` 或直接 `@app.post()` 引用 `webhook_router` 的处理函数。

### 2. Webhook 配置文件：`config/webhooks.yaml`

延续 `config/mcp.yaml` 的模式，`server.py` lifespan 启动时加载，不存在则跳过（webhook 功能可选）。

```yaml
sources:
  - id: github-ci
    secret: "sha256-hmac-secret"   # optional, skip verify if absent
    user_id: "uuid-of-internal-user"
    agent_name: "devops"           # optional, falls back to channel/default agent
    message_template: "GitHub {event}: {repository[full_name]} — {head_commit[message]}"
```

`message_template` 使用 Python `str.format_map(FlatDict(payload))` 提取 payload 字段（支持一层嵌套 `{key[subkey]}`）。格式字符串解析失败时 fallback 到 `json.dumps(payload)`。

### 3. 签名验证：`X-Hub-Signature-256: sha256=<hex>`

这是 GitHub / GitLab / 大多数 CI 系统的标准头。验证逻辑：
```python
import hmac, hashlib
expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
hmac.compare_digest(expected, header_value)  # 防时序攻击
```
签名不匹配 → 返回 403。source 不存在 → 返回 404。

### 4. 复用 `normalizer.route()` pipeline

Webhook 用户（`user_id` 来自配置）是内部用户，`im_user_store.check_allowed_by_user_id()` 对无 im_users 记录的用户返回 `True`，allowlist 检查天然放行。

`reply_func` 设为 no-op async 函数——agent 运行结果写入 eval trace，不需要回推。

`session_id` 用 `f"webhook-{source_id}"`：同一 source 的所有事件共享一个持久 session，agent 有上下文连续性（如 CI 失败可以看到历史）。

### 5. 202 Accepted + asyncio.create_task

响应即时返回，agent run 用 `asyncio.create_task()` 在后台执行。与现有 Slack/Telegram 适配器的处理方式一致（都是 fire-and-forget）。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 外部系统重试导致重复 agent run | 第一版不做幂等（无 delivery_id 去重），接受偶发重复；日志可排查 |
| message_template 字段路径写错导致 fallback 到 json.dumps | 错误 silently fallback，trace 里有完整 payload，不会静默丢失 |
| 共享 session 导致 webhook 事件间上下文污染 | 可在 config 中设 `session_per_event: true`（后续扩展），第一版用共享 session |
| 无 secret 配置时任何人可触发 | 文档中明确说明：无 secret 仅适合内网；生产环境必须配 secret |

## Migration Plan

1. 新增 `webhook_router.py`（纯新代码）
2. `server.py` lifespan 加载 `config/webhooks.yaml`，注册路由
3. 提供 `config/webhooks.example.yaml` 示例文件
4. 无数据迁移，无现有行为变更
