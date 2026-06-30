## Context

`webhook-triggers` spec 已定义入站 webhook 触发 agent run 的行为（`POST /webhook/{source_id}` → 202、HMAC-SHA256 `X-Hub-Signature-256`、`message_template` format_map、后台 `normalizer.route()`、`session_id="webhook-{source_id}"`、`webhooks.enabled`/`max_body_bytes`），`src/fleetent/webhook_router.py` 已实现 `WebhookSource` 模型、`extract_message`、`verify_signature` 纯函数。但**端点未挂载**（无人 import）、**运行时 source 管理被推迟**、YAML 加载废弃。

现有部署是 platform + node + agent 三层：managed 下 agent 由 node 拉起（注入 `FLEETENT_NODE_*`，`--no-im`，IM 由 node edge 托管），standalone 下 `fleetent agent run` 自托管 HTTP（`runtime/agent_app.py`）。约束：agent⊥platform 单向解耦；手写 SQL 经 store 边界；secret 不明文落库。

## Goals / Non-Goals

**Goals:**
- 把 webhook 接成 live：两态对称端点 + 运行时 source 管理。
- 最大化复用既有件：`webhook_router.py`、platform→node→agent 转发（`agent_transport`）、directed-reach 出站（`outbound`）、secret 加密（`secret_crypto`）。
- standalone 与 managed 并存，模式自动判别（不新增 mode 配置）。

**Non-Goals:**
- 前端管理 UI、限速/防滥用、channel 回投目标、白名单免审批、webhook 重放/重试队列（均后续切片）。

## Decisions

- **D1 两态对称，模式判别沿用 `is_node_managed_runtime()`**：不引入 `mode` 配置。standalone：`agent_app` 挂 `POST /webhook/{source_id}`，source 读 `agent.yaml`，本进程后台 `normalizer.route()`。managed：platform 挂公开端点，source 读管理库，校验后经 `agent_transport.webhook()` → node **`/forward/agents/{name}/webhook/{source_id}`** 转发到 **agent 自身的 `/webhook` edge**（而非 `/chat`），由该 edge 构 `NormalizedMessage` 后台 route——两态因此共用同一 agent 侧处理器与回投接线。平台已校验 HMAC，故经可信 `X-Fleetent-Webhook-Source` 头把解析后的 source（user_id/template/reply_target）注入 agent，agent 跳过二次 HMAC（同 ingress principal 头的信任模型）。**备选**：managed 转发到 `/chat`（否：`/chat` 无法携带 reply_target/身份，回投做不成、破坏两态对称）。

- **D2 source 存储两态 + secret 类型感知**：managed 新增 Alembic 表 `webhook_sources`，secret 用 Fernet 密文存行内（platform 入站端解密做 HMAC——secret 是平台校验用、非 agent env 凭据，故不走 `agent_secrets`）；standalone 走 `agent.yaml` `webhooks.sources`，secret 用 `secret_env` env 引用（同 MCP `key_env`）。两态都经 `webhook_router.WebhookSource` 统一模型。**备选**：secret 走 agent_secrets（否：语义错位——HMAC 在 platform 侧校验、不注入 agent env）。

- **D3 端点逻辑收敛到中立纯函数 + 薄 face**：`webhook_router` 继续承载 HMAC/模板/模型（补 `reply_target` 字段）；standalone face（agent_app 路由）与 managed face（platform 端点）各自薄封装：查 source → enabled/body 闸 → `verify_signature` → `extract_message` → 构 `NormalizedMessage` → 202 + 后台 route/转发。两 face 共用 `webhook_router`，互不 import。

- **D4 回投（A/B/C）**：两态共用同一 `reply_func`——`reply_func(text)` 在 source 配了 `reply_target`（本轮=内部 user_id）时调 `outbound_connectors.notify_user(reply_target, text)`，未配则 no-op（A/C，结果进 trace）。`notify_user` 自身在**非 node-managed 运行时即为 no-op**，故同一接线在 managed-agent 进程内投递（→ im_outbound_queue → node drain → DM）、在 standalone dev 进程内自然降级为 no-op，无需按模式分支。尽力而为、失败只记日志。

- **D5 治理轻量**：以 source 的 `user_id` 身份跑，走和 IM 完全一致的 `permission_gate`/approval，无 webhook 专属审批/白名单/限速（YAGNI）。需审批的高风险动作在无人在环下按现有 `on_no_approver` 策略处理（默认 reject），不特殊化。

- **D6 managed admin API**：`platform/webhook_management/` 提供 admin-鉴权 REST CRUD（复用 `connector_admin_api` 模式）+ `webhook_source_store`（管理库读写、secret 加解密）。前端 UI 后续。

## Risks / Trade-offs

- [managed 转发同步等待 vs 入队]：用 `agent_transport` 同步转发最简且复用现成通道；webhook 已先回 202，转发在后台 task 里做，node/agent 不可达时只记日志（不影响已返回的 202）。重试队列留后续。
- [reply_target 仅支持 user_id DM]：channel 回投需要 node 连接器寻址，本轮不做；A/C（no-op + agent 自发）已覆盖大多数场景。
- [secret 明文经 HTTP 提交到 admin API]：仅 admin 鉴权通道、密文落库、响应不回显；与现有 connector secret 提交同等保护。
- [遗留 YAML `load_sources`]：保留函数但不再被 face 调用（标注废弃）；spec 已要求遗留 YAML 不加载。

## Open Questions

- 无（brainstorming 锁定；managed 转发的具体 transport 调用、reply_func 接线细节在 apply 阶段按既有范式定）。
