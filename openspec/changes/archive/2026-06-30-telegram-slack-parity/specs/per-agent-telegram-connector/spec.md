## ADDED Requirements

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
