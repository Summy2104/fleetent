# per-agent-telegram-connector Specification

## Purpose
Per-agent Telegram connectivity: each agent declares its own Telegram bot in agent.yaml, is supervised by agent name from the agent index, resolves the agent implicitly from the receiving connection, and filters chats — mirroring per-agent-slack-connector. The adapter carries no platform dependency.

## Requirements

### Requirement: agent.yaml declares a Telegram connector

An agent SHALL declare its Telegram connection in its `agent.yaml` under
`im.telegram` with `bot_token_env` (an environment-variable name, never an inline
token) and an optional `access: ImAccess` block. The `channels` field is removed;
chat filtering is handled by `access.allow_groups`. The token SHALL be resolved from
the named environment variable at connection time. The config scanner SHALL reject inline
plaintext secrets anywhere under `im`.

#### Scenario: Connector parsed with env reference

- **WHEN** an `agent.yaml` declares `im.telegram` with `bot_token_env: SALES_TG_BOT`
- **THEN** the agent loads with a Telegram connector whose token resolves from that env var

#### Scenario: Inline token rejected

- **WHEN** an `agent.yaml` sets `im.telegram.bot_token_env` to an inline token-like
  value instead of an env-var name
- **THEN** the scan fails fast, naming the agent and field

#### Scenario: No connector block

- **WHEN** an `agent.yaml` has no `im.telegram`
- **THEN** the agent loads normally and no Telegram connection is started for it

#### Scenario: Connector with access block

- **WHEN** an `agent.yaml` declares `im.telegram` with `access.require_approval: false`
- **THEN** the agent loads and unknown Telegram users are rejected silently (not queued as pending)

### Requirement: One Telegram connection per declaring agent

The system SHALL run exactly one Telegram polling connection per agent whose
`im.telegram` env token resolves, supervised by agent name and sourced from the
agent index. Startup SHALL start a connection for every such agent. An agent whose env
token is missing SHALL be reported unconfigured and skipped without affecting other
agents' connections.

#### Scenario: Two agents each get their own connection

- **WHEN** agents `support` and `sales` each declare `im.telegram` with a resolvable
  env token and startup runs
- **THEN** two independent Telegram connections are started, one per agent

#### Scenario: Missing token isolates failure

- **WHEN** agent `support` declares `im.telegram` but its `bot_token_env` variable
  is unset, while `sales` resolves fine
- **THEN** `support` is reported unconfigured and skipped, and `sales` still starts

### Requirement: Reload reconciles connections against the agent index

The supervisor SHALL provide a reload that re-scans the agent index and reconciles running
connections against declared ones: starting newly declared agents, stopping removed ones,
and restarting agents whose connector config changed.

#### Scenario: New agent added then reloaded

- **WHEN** a new agent declaring `im.telegram` is added and reload runs
- **THEN** a connection is started for the new agent without restarting the others

#### Scenario: Agent removed then reloaded

- **WHEN** an agent that had a running Telegram connection is removed and reload runs
- **THEN** that agent's connection is stopped and removed

### Requirement: Telegram connection status is supervisor-owned, not platform-written

Per-agent Telegram connection status SHALL be owned in-memory by the supervisor
(`unconfigured`/`connecting`/`connected`/`stopped`/`error`). The Telegram adapter SHALL
NOT write status or heartbeat to any platform store and SHALL NOT import
`fleetent.platform`.

#### Scenario: Status transitions tracked by the supervisor

- **WHEN** an agent's Telegram connection starts, then is stopped
- **THEN** the supervisor reports `connected` then `stopped` for that agent, without any
  write to the owner-level `im_connectors` table

#### Scenario: Adapter has no platform dependency

- **WHEN** the Telegram adapter module is imported
- **THEN** it does not import `fleetent.platform`

### Requirement: Telegram routing resolves the agent implicitly from the connection

For Telegram, the agent SHALL be determined by the connection that received the update, not
by a channel→agent lookup. The adapter SHALL stamp the resolved agent onto the
`NormalizedMessage`, and routing SHALL use it directly. Chat filtering (formerly
`im.telegram.channels`) is now handled by the access gate via `access.allow_groups`.

#### Scenario: Message handled by the receiving agent

- **WHEN** a Telegram message arrives on agent `sales`'s connection
- **THEN** the message is processed with agent `sales`'s snapshot, with no channel→agent lookup

#### Scenario: Chat filter via access.allow_groups

- **WHEN** agent `sales` sets `im.telegram.access.allow_groups: ["-100123"]` and a message
  arrives in chat `-100999`
- **THEN** the message is rejected by the access gate

#### Scenario: Empty allow_groups responds everywhere

- **WHEN** agent `sales` omits `im.telegram.access.allow_groups` (or leaves it empty)
- **THEN** the agent responds in every chat its Telegram bot receives updates from

### Requirement: Connector carries no owner_id and reads no platform table

The Telegram connector path SHALL NOT thread an `owner_id` and SHALL NOT read any platform
management table (notably `users`), mirroring `per-agent-slack-connector` and preserving the
adapter's "no platform dependency" contract. The supervisor's runner signature SHALL be
`(agent_name, config)` — no `owner_id` argument — and `telegram.run` / `create_app` SHALL NOT
accept an `owner_id`. The inbound `NormalizedMessage` SHALL NOT carry an `owner_id` field.
Session identity SHALL be derived without an owner prefix: the routed `session_id` equals
the adapter-derived session id, NOT `f"{owner_id}:{session_id}"`. Chat access remains
enforced by the access gate against `msg.user_id` and the connector `access` block.

#### Scenario: Standalone connector starts without a users table

- **WHEN** `fleetent agent run` starts a Telegram connector in an environment where the
  platform `users` table does not exist
- **THEN** the connection starts, the supervisor never reads a platform table, and no
  `no such table: users` error is logged

#### Scenario: Session id has no owner prefix

- **WHEN** a Telegram message is routed
- **THEN** the session id used for load/save/lock is the adapter-derived id with no
  `<owner>:` prefix

### Requirement: Telegram 审批按钮回调承接

Telegram 适配器 MUST 注册一个 callback-query handler 承接审批按钮点击，镜像 Slack 的审批按钮处理（`handle_approval_action`）。该 handler SHALL 只处理 `callback_data` 以审批前缀（`approval:`）开头的回调，其余回调 MUST NOT 误归本 handler。`callback_data` SHALL 紧凑编码 `decision`（`approve`/`reject`/`approve_always`）与 `approval_id`，整体长度 MUST NOT 超过 Telegram 的 64 字节上限。

承接到点击后，handler SHALL：先 ack 回调；以点击者的 Telegram user id 为决策者；复用既有中立审批件——经 `approval_store` 取该 `approval_id` 的 `session_id`、经 `session_manager` 取该会话 pending 项的授权 actor 集，调用中立的审批决议入口（`resolve_approval_request`）落账。决策者不在授权集时，决议 MUST NOT 生效，handler SHALL 用一次性提示（`answer` 的 alert）告知无权或已处理、并保留按钮。决议生效时，handler SHALL 把原提示消息改写为结果态并移除内联键盘以防重复点击，随后经中立恢复入口（`_resume_pending_in_session`）恢复挂起的 run。恢复失败 SHALL 只记日志、MUST NOT 回滚已落的决议。本 handler MUST NOT `import fleetent.platform`。

#### Scenario: 授权用户点击批准恢复 run

- **WHEN** 审批者在 Telegram 审批提示上点击"同意"，且其 user id 在该审批的授权 actor 集中
- **THEN** 决议记为 approved、原提示被改写为结果态且移除按钮、挂起的 run 经中立恢复入口被恢复

#### Scenario: 非授权用户点击被拒

- **WHEN** 非授权用户点击审批按钮
- **THEN** 决议 MUST NOT 生效，该用户收到一次性 alert 提示无权/已处理，按钮保留

#### Scenario: 决议已处理或过期

- **WHEN** 点击的 `approval_id` 已被处理或已过期（中立决议入口返回未命中）
- **THEN** handler 用一次性 alert 提示、不改写消息、不恢复 run

#### Scenario: 非审批回调不被误处理

- **WHEN** 一个 `callback_data` 不以审批前缀开头的回调到达
- **THEN** 审批 handler MUST NOT 处理它

### Requirement: Telegram reply_func 支持可选交互动作

Telegram 适配器构造的 `reply_func` SHALL 接受可选的交互动作集（审批 approve/reject/approve_always），对标 Slack `reply_func(text, blocks)`。未提供动作时行为 SHALL 与既有纯文本回复一致；提供动作时 SHALL 渲染为内联键盘随消息一并发送，使 `permission_gate` 的 requester-reply 路径在 Telegram 也能呈现审批按钮。

#### Scenario: 无动作时纯文本回复不变

- **WHEN** `reply_func` 仅以文本调用（无交互动作）
- **THEN** 发送一条纯文本消息，行为与既有一致

#### Scenario: 带审批动作时附内联键盘

- **WHEN** `reply_func` 以文本 + 审批动作集调用
- **THEN** 该消息附带内联键盘，按钮的 `callback_data` 编码对应 `approval_id` 与 decision

### Requirement: Telegram 入站接收非图片文件

Telegram 适配器的消息 handler filter SHALL 在保留图片（`PHOTO`，走既有视觉路径）的同时接收文档/文件（`Document`）。详见 `im-file-attachment` capability 中"Telegram 适配器下载非图片文件为文件附件项"。

#### Scenario: 文档消息被 handler 接收

- **WHEN** 用户向 Telegram bot 发送一个文档（非图片文件）
- **THEN** 消息 handler 接收它（不再因仅 `PHOTO` filter 而被忽略）

### Requirement: Telegram 入站接线生成图片自动回投

Telegram 适配器构造的入站 `NormalizedMessage` SHALL 设置 `upload_func`，使本轮 agent 产出的生成图片/文件自动投回原会话，镜像 Slack 行为。详见 `im-generated-image-upload` capability 中"Telegram 适配器上传生成图片到原会话"。

#### Scenario: 入站消息携带 upload_func

- **WHEN** Telegram 适配器构造入站 `NormalizedMessage`
- **THEN** 其 `upload_func` 非空，指向本会话的文件投递
