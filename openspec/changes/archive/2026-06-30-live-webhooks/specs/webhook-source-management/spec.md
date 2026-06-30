## ADDED Requirements

### Requirement: webhook source 运行时存储两态

webhook source 的存储 SHALL 两态对称。managed 下 source MUST 持久化在管理库表 `webhook_sources`（经 Alembic 迁移建立，手写 SQL 经 store 边界、named parameters、无 ORM），字段含 `id` / `agent_id`(FK→agents.id) / `user_id` / `message_template` / `reply_target`（可空）/ `enabled` / secret 密文列。standalone 下 source SHALL 取自 `agent.yaml` 的 `webhooks.sources` 列表（每项含 `id` / `user_id` / `agent_name`（可省，默认本 agent）/ `message_template` / `reply_target` / `secret_env`）。两态的 source 都经中立 `webhook_router` 的同一 `WebhookSource` 模型表达。

#### Scenario: managed source 落管理库
- **WHEN** 在 managed 下登记一个 webhook source
- **THEN** 该 source 持久化为管理库 `webhook_sources` 行，platform 入站端按 `source_id` 查得

#### Scenario: standalone source 取自 agent.yaml
- **WHEN** standalone agent 的 `agent.yaml` 配了 `webhooks.sources`
- **THEN** agent 启动后这些 source 可被 `POST /webhook/{source_id}` 命中

### Requirement: webhook secret 类型感知存储，平台不持明文

webhook source 的 `secret`（HMAC 校验用）MUST NOT 以明文持久化。managed 下 secret SHALL 以 Fernet 密文存于 `webhook_sources` 行内（复用 `secret_crypto`），HMAC 校验在 platform 入站端解密使用——secret 是平台入站校验用、并非注入 agent env 的凭据，故存行内而非 `agent_secrets`。standalone 下 secret SHALL 以 `secret_env`（env 变量名引用，同 MCP `key_env` 风格）表达，值经 agent 进程环境取用，明文不入 `agent.yaml`。

#### Scenario: managed secret 密文存储
- **WHEN** 登记带 secret 的 managed webhook source
- **THEN** 库行内的 secret 列是 Fernet 密文，明文不出现在表中；HMAC 校验时解密使用

#### Scenario: standalone secret 走 env 引用
- **WHEN** `agent.yaml` 的 source 配 `secret_env: MY_WEBHOOK_SECRET`
- **THEN** 校验时从环境变量 `MY_WEBHOOK_SECRET` 取 secret 值；`agent.yaml` 内无明文 secret

### Requirement: managed webhook source 经 admin REST API 管理

managed 下系统 SHALL 提供受管理员鉴权的 REST API 对 `webhook_sources` 做增删查改（CRUD）。创建/更新 MUST 校验必填字段（`id` / `user_id`；`agent_id` 用于路由目标 agent，未配则入站投递时拒绝）；非管理员会话 MUST 被拒。secret 提交后 MUST 以密文落库、响应 MUST NOT 回显明文 secret。

#### Scenario: 管理员创建 source
- **WHEN** 管理员 POST 一个 webhook source（含 secret）到 admin API
- **THEN** source 落管理库、secret 密文存储，响应不含明文 secret

#### Scenario: 列出/删除 source
- **WHEN** 管理员 GET 列表或 DELETE 某 `source_id`
- **THEN** 返回不含明文 secret 的 source 列表 / 删除该 source 后 `POST /webhook/{id}` 返回 404
