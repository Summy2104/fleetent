## 1. governance 去泄漏：gate 发中立审批意图，Slack 渲染下沉 outbound 边界（Slack 输出不变）

- [x] 1.1 写测试(红)：`permission_gate` 构建审批提示时产出平台无关的审批意图（approval_id + 动作集 approve/reject/approve_always + summary），且模块 MUST NOT import `approval_prompt_blocks`；outbound 边界对 Slack 渲染的输出与原 `approval_prompt_blocks(...)` 逐字节一致（回归基线）。unit。
- [x] 1.2 实现(绿)：定义中立 `ApprovalPrompt` 意图；`permission_gate` 改发意图（移除对 `approval_prompt_blocks` 的 import/调用）；outbound 发送边界（`send_to` 与平台 reply 渲染）按 `platform` 分发，Slack 分支调既有 `approval_prompt_blocks`（输出不变）。

## 2. Telegram 审批按钮渲染 + callback_data 编解码

- [x] 2.1 写测试(红)：`render_approval_telegram(approval_id, summary)` 产 `InlineKeyboardMarkup`，三按钮 callback_data 经 `encode/decode` 往返得 (decision, approval_id)，且长度 ≤64 字节；非 `approval:` 前缀 decode 返回 None。unit。
- [x] 2.2 实现(绿)：`outbound.render_approval_telegram` + callback_data `encode/decode`（`approval:{decision}:{approval_id}`）。

## 3. Telegram reply_func 支持可选交互动作 + _telegram_send keyboard

- [ ] 3.1 写测试(红)：Telegram `reply_func` 无动作=纯文本（行为不变）、有审批动作=随消息带内联键盘；`_telegram_send` 接受并传递 `reply_markup`。unit（stub bot）。
- [ ] 3.2 实现(绿)：`telegram.py` `reply_func` 扩为 `(text, actions=None)`；`_telegram_send` 支持 `reply_markup`。

## 4. Telegram 审批 callback handler（授权/恢复/防重复，镜像 slack.handle_approval_action）

- [ ] 4.1 写测试(红)：`handle_approval_callback`——授权用户点击→`resolve_approval_request` 落账 + `edit_message_text` 去键盘 + `_resume_pending_in_session` 被调；非授权→决议不生效 + `answer(show_alert)` 提示 + 保留键盘；未命中(已处理/过期)→alert 不改写不恢复；非 `approval:` 前缀回调不处理；恢复抛错只记日志不回滚。unit（mock 中立件 `approval_store`/`session_mgr`/`resolve_approval_request`/`_resume_pending_in_session`，stub bot+callback，对照现有 Slack handler 测试风格）。
- [ ] 4.2 实现(绿)：`telegram.create_app` 注册 `CallbackQueryHandler`，实现 `handle_approval_callback`（ack→解析→授权→resolve→edit→resume，best-effort）；MUST NOT import platform。

## 5. 非图片文件入站（filters.Document + 下载/降级）

- [ ] 5.1 写测试(红)：`_download_document_attachments` 成功→`FileAttachment(data,mime,filename)`；超 20MB→`data=None` 占位(note 超限)；下载失败→记 warning + `data=None` 占位(note 失败)、不抛异常；handler filter 含 `Document`（图片仍走 PHOTO）。unit（stub bot/get_file）。
- [ ] 5.2 实现(绿)：handler filter 加 `filters.Document`；新增 `_download_document_attachments`（bot get_file→下载、大小上限、失败/超限降级），并入 `NormalizedMessage.attachments`。

## 6. 生成图片自动回投（入站 upload_func）

- [ ] 6.1 写测试(红)：Telegram 入站构造的 `NormalizedMessage.upload_func` 非空；调用它→经 `outbound.send_file_to`(platform=telegram, 本会话地址) 投递；单文件失败被吞不抛。unit（mock send_file_to）。
- [ ] 6.2 实现(绿)：`telegram.py` 入站设 `upload_func`，镜像 `slack._make_upload_func`→`send_file_to`，复用 `ConversationAddress`。

## 7. 闭环 + 守护 + 收尾

- [ ] 7.1 写守护/契约测试(红→绿)：`im_gateway/telegram.py` 不 import platform；`permission_gate` 不再 import `approval_prompt_blocks`（去泄漏断言）；Slack 审批渲染输出回归基线不变。
- [ ] 7.2 跑 `make test-pr` + `make test-integration-ci`（FLEETENT_HOME 隔离），对照 main 基线无新增失败；**特别确认全部 Slack 审批单测/集成全绿（Slack 行为零改动硬目标）**；模块/层/plane 守护通过。
- [ ] 7.3 `openspec validate telegram-slack-parity` 通过；归档前确认所有 checkbox 为 [x]。
