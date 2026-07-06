# webhook-source-management Specification

## Purpose
运行时 webhook source 的存储与管理：managed 持久化于管理库 `webhook_sources`（Fernet 密文 secret + admin REST CRUD），standalone 取自 `agent.yaml` 的 `webhooks.sources`（`secret_env` 引用）。两态经中立 `webhook_router.WebhookSource` 统一表达。

## Requirements

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

更新 SHALL 经 `PUT /admin/webhooks/sources/{id}` 实现，且 `id` 不可变更（`id` 即公开 URL `/webhook/{id}`）。更新的密钥处理 MUST 由显式判别字段 `secret_action` 决定，MUST NOT 因请求体缺省 secret 而清空已有密钥：

- `keep`（默认）→ 保持已有密钥不变（物理上不触碰 secret 密文列）；
- `set` → 用请求体 `secret` 新值加密覆盖（`set` 时 `secret` 缺失 MUST 返回 400）；
- `clear` → 将密钥置空。

对不存在的 `id` 更新 MUST 返回 404。

#### Scenario: 管理员创建 source
- **WHEN** 管理员 POST 一个 webhook source（含 secret）到 admin API
- **THEN** source 落管理库、secret 密文存储，响应不含明文 secret

#### Scenario: 列出/删除 source
- **WHEN** 管理员 GET 列表或 DELETE 某 `source_id`
- **THEN** 返回不含明文 secret 的 source 列表 / 删除该 source 后 `POST /webhook/{id}` 返回 404

#### Scenario: 管理员更新 source 常规字段，默认保留密钥
- **WHEN** 管理员 PUT 一个已有 `source_id`，改动 user_id / agent_id / message_template / reply_target / enabled，且 `secret_action` 缺省（keep）
- **THEN** 常规字段更新落库，已有密钥保持不变，响应不含明文 secret 但 `has_secret` 仍为 true

#### Scenario: 管理员更换或清除密钥
- **WHEN** 管理员 PUT 时 `secret_action="set"` 并带新 `secret` / 或 `secret_action="clear"`
- **THEN** 密钥被新值密文覆盖 / 被置空（`has_secret` 变 false）；`set` 缺 secret 返回 400

#### Scenario: 更新不存在的 source
- **WHEN** 管理员 PUT 一个不存在的 `source_id`
- **THEN** 返回 404，不新建行

### Requirement: managed webhook source 在 React SPA 中原生管理

React 管理 SPA SHALL 提供托管 webhook source 的原生管理界面：列表、新建、**查看全部字段**、**编辑**、删除。创建/编辑表单 MUST 要求 `id` / `user_id` / `agent_id` 必填（`agent_id` 前端强制必填，即使后端模型允许 null——入站请求在 `agent_id` 为空时会 409）；`id` 在编辑态 MUST 只读。查看/编辑 SHALL 经同一弹窗，默认只读展示除密钥外的全部字段（`reply_target` / `agent` 显示名称、密钥仅显示「已设置/未设置」），点「编辑」切到可改态。编辑保存的密钥处理 MUST 提供「保持（默认）/ 更换 / 清除」三种显式动作，映射到后端 `secret_action`，SPA MUST NOT 回显明文 secret。

#### Scenario: 管理员新建 webhook source
- **WHEN** 管理员在 SPA 中填写 id / user_id / agent_id 等字段并提交新建
- **THEN** SPA 调用 `POST /admin/webhooks/sources`，成功后列表刷新，并展示可复制的完整 webhook URL

#### Scenario: 管理员查看 webhook source 全部字段
- **WHEN** 管理员对某条 webhook source 打开「查看/编辑」弹窗
- **THEN** 弹窗只读展示 id / agent 名 / user / reply_target 名 / message_template / 启用状态 / 密钥「已设置或未设置」，不回显明文 secret

#### Scenario: 管理员编辑 webhook source
- **WHEN** 管理员在弹窗点「编辑」，改动常规字段并保存，密钥保持默认不动
- **THEN** SPA 调用 `PUT /admin/webhooks/sources/{id}`（`secret_action=keep`），成功后列表刷新、弹窗回只读态，已有密钥不受影响

#### Scenario: 管理员更换或清除密钥（SPA）
- **WHEN** 管理员在编辑态选「更换密钥」填新值 / 或选「清除密钥」并保存
- **THEN** SPA 分别以 `secret_action=set`（带新 secret）/ `secret_action=clear` 调 PUT，密钥被更换 / 清除

#### Scenario: 管理员删除 webhook source
- **WHEN** 管理员对某条 webhook source 发起删除并确认
- **THEN** SPA 调用 `DELETE /admin/webhooks/sources/{id}`，成功后该行从列表消失
