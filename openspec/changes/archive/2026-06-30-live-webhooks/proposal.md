## Why

`webhook-triggers` spec 已定义入站 webhook 触发 agent run，但**端点从未接线**（无人 import `webhook_router`、无 `/webhook` 路由）、**运行时 source 管理被显式推迟**（"由后续 webhook source management change 处理"）、YAML source 加载已废弃。结果：webhook 是"设计好但不可用"的死代码。本变更把它接成 live 功能，作为外部系统（CI / GitHub / 任意第三方）事件驱动 agent 的入口。

## What Changes

- **接线两态对称的 webhook 端点**（仿现有 IM 入站，不新增 mode 配置，沿用 `outbound_connectors.is_node_managed_runtime()` 自动判别）：
  - **standalone**：`runtime/agent_app.py` 挂 `POST /webhook/{source_id}`，source 读 `agent.yaml`，后台 `normalizer.route()`。
  - **managed**：platform 挂公开 `POST /webhook/{source_id}`，source 存管理库，校验后经现有 platform→node→agent 通道转发给目标 agent。
- **运行时 source 管理**（补齐被推迟的缺口）：
  - managed：新增管理库表 `webhook_sources`（Alembic），secret 以 Fernet 密文存行内；admin REST API CRUD。
  - standalone：`agent.yaml` 的 `webhooks.sources`，secret 走 `secret_env` env 引用。
- **请求流**：查 source（无→404）→ `webhooks.enabled` 与 body≤`max_body_bytes` 闸 → HMAC-SHA256（`X-Hub-Signature-256`，失败 403）→ 模板提取消息 → 立即 **202** + 后台 run（`session_id="webhook-{source_id}"`）。
- **可选回投**：per-source `reply_target` 未配 → reply no-op（结果进 eval trace）；配了 → 把 run 结果投到该 IM 目标（managed 复用 directed-reach 出站 `notify_user`，standalone 走 agent 连接器）。
- 复用既有 `webhook_router.py`（HMAC/模板/source 模型纯函数）。

## Capabilities

### New Capabilities
- `webhook-source-management`: webhook source 的运行时存储与管理——managed（管理库表 `webhook_sources` + secret 密文 + admin REST API CRUD）与 standalone（`agent.yaml` `webhooks.sources` + `secret_env`）两态；取代被废弃的 YAML 加载。

### Modified Capabilities
- `webhook-triggers`: 补齐"端点接线 + 两态对称拓扑（standalone agent_app / managed platform→node→agent）+ 模式判别沿用 `is_node_managed_runtime` + 可选 `reply_target` 回投（默认 no-op）"；HMAC/模板/202/session 行为不变。

## Impact

- **owning packages**：`webhook_router.py`（中立纯函数，已在，补 reply_target 字段）；standalone 端 `runtime/agent_app.py` + `agent_config.py`（`WebhooksSettings.sources`）；managed 端新 `platform/webhook_management/`（端点 + CRUD + `webhook_source_store`），转发复用 `platform/node_management/agent_transport`；回投复用 `outbound.py` directed-reach。
- **owned tables**：`webhook_sources`（管理库，Alembic 新迁移；secret 密文列）。
- **config namespace**：platform `webhooks.*`（`enabled`/`max_body_bytes`，已在）+ agent.yaml `webhooks.sources`。
- **cross-module deps**：严守 agent⊥platform——standalone 端点在 `agent_app` 内 MUST NOT import platform；managed 端点在 platform 侧；中立 `webhook_router` 两侧共用。
- **migration/shim**：新增 `webhook_sources` Alembic 表；YAML `load_sources` 标注废弃（spec 已要求遗留 YAML 不再加载）。
- **Non-Goals**：前端管理 UI、限速/防滥用、channel 回投目标、白名单免审批、webhook 重放/重试队列（均后续）。
