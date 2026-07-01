## Context

Telegram 适配器（`im_gateway/telegram.py`）已实现入站文本/图片、出站文本/文件、typing 心跳、`reply_func`/`progress_func`/`outbound_connectors`/`conversation_address` 接线，per-agent 由 `TelegramSupervisor` 托管、node `im_edge` 在 managed 下持有 polling 连接并把入站 `NormalizedMessage` 转发到 agent `/im/route`。相对最成熟的 Slack 渠道仍差三块（见 proposal）。

约束：agent⊥platform 单向解耦——`im_gateway/*` 是 no-platform-import edge face；审批的授权/落账/恢复逻辑已在中立件中实现（`approval_router.resolve_approval_request`、`session_mgr.get_pending_approval`、`normalizer._resume_pending_in_session`），两平台共用、本 change 不改。对 Slack 行为零改动是硬目标。

## Goals / Non-Goals

**Goals**：Telegram 达到与 Slack 一致的能力矩阵——审批按钮（含 managed 两态）、非图片文件入站、生成图片/文件自动回投；顺带修正 `permission_gate` 对 Slack 渲染格式的分层泄漏（对齐既有 spec「gate 不透明传递交互 payload」的意图）。

**Non-Goals**：slash command、clarify 按钮、富 Block Kit 排版对齐、WhatsApp。

## Decisions

- **D1 方案 B：按平台各自渲染，不引入中立 descriptor 框架。** 代码库既有范式即"按平台 renderer 函数"（`render_clarify_slack/telegram/text`、`_slack_send/_telegram_send`），无"中立 descriptor + 分发"抽象。审批的高危逻辑（授权/落账/恢复）早已中立共享，A 方案能"中立化"的仅剩按钮渲染，而渲染天生平台特定（Block Kit vs InlineKeyboard 仅共享 `label+approval_id` 这类 trivial 数据）。故新增 `render_approval_telegram` 与既有 `approval_prompt_blocks` 平级，由 outbound 边界按 `platform` 分发。**备选 A（中立 descriptor 抽象）**：逆代码库纹理、改动 Slack 渲染路径、收益基本是幻觉，否决。

- **D2 governance 去泄漏：gate 发中立审批意图、渲染下沉 outbound 边界。** `permission_gate`（`governance/`，声明 No platform imports）当前 `import approval_prompt_blocks` 并构造 Slack 形状 blocks，是分层泄漏，且与 permission-gate spec「gate 不知平台渲染细节、不透明传递」矛盾。改为：gate 发最小中立审批意图 `ApprovalPrompt(approval_id, summary, actions=[approve|reject|approve_always])`；outbound 发送边界（`send_to` 与各平台 `reply_func`）按 `platform` 渲染——Slack 调 `approval_prompt_blocks`（**输出逐字节不变**，仅调用点从 gate 移到边界），Telegram 调 `render_approval_telegram`。Slack `handle_approval_action` 入站 handler 不动。

- **D3 Telegram 审批入站 callback：镜像 `slack.handle_approval_action`。** `telegram.py` 注册 `CallbackQueryHandler`（`callback_data` 前缀 `approval_`）。handler：解析 `callback_data`（`approval_id`+`decision`）→ `callback.from_user.id` 为决策者 → `callback.answer()` 先 ack → 复用 `approval_store.get_approval` 取 `session_id`、`session_mgr.get_pending_approval` 取授权 actor 集 → `resolve_approval_request(...approver_user_id=clicker, authorized_actors=...)` → 未命中：`callback.answer(text=..., show_alert=True)` 提示无权/已处理、保留键盘 → 命中：`edit_message_text` 改成结果态去键盘防重复点 → `normalizer._resume_pending_in_session(resume_msg, session_id, approval_id, decision)` 恢复挂起 run。恢复失败只记日志、不回滚已落决议（best-effort，与 Slack 一致）。

- **D4 `callback_data` 编码：紧凑且 ≤64 字节（Telegram 上限）。** 用 `f"approval:{decision}:{approval_id}"`（decision ∈ `approve|reject|approve_always`）；`approval_id` 为短 id，整体远小于 64B。解码用前缀 split，非 `approval:` 前缀的 callback 不归本 handler。

- **D5 Telegram `reply_func` 扩展为 `(text, actions=None)`。** 默认无 actions 时行为不变（纯文本）；有 actions 时渲染 `InlineKeyboardMarkup` 一并发送。permission_gate 的 requester-reply 路径因此也能在 Telegram 出按钮（对标 Slack `reply_func(text, blocks)`）。

- **D6 非图片文件入站：filter 加 `filters.Document`，新增 `_download_document_attachments`。** 镜像 Slack `_download_attachments` 语义：用 bot 取 `file_id` 的下载 URL，按大小上限（20MB，与 Slack 一致）判断；超限/失败构造 `data=None` 占位 `FileAttachment(note=...)`，不抛异常中断；成功构造 `FileAttachment(data, mime, filename)`。图片仍走既有 `filters.PHOTO` 视觉路径不变。Telegram 文件下载经 bot API（`get_file` → `file_path` → 下载），无 Slack 那种 302 跨域/HTML 登录页问题，故降级分支仅覆盖超限与下载失败。

- **D7 生成图片自动回投：入站设 `upload_func`。** 镜像 `slack._make_upload_func`：`telegram.py` 入站构造 `upload_func(paths)` → `outbound.send_file_to(平台=telegram, 地址=本会话 ConversationAddress, paths)`，使 `generate_image` 等本轮产物自动投回原会话（私聊/群组/话题）。失败被 `send_file_to` 吞、不阻断 run。

- **D8 托管两态对称。** callback handler 注册在 `create_app`（agent 侧），managed 下由 node 托管的 `TelegramSupervisor` 的 polling Application 承接 callback，handler 调用的中立件（approval store/session/resume）在 node 进程可达——与 Slack `handle_approval_action` 在 managed 下的进程局部性完全同构，无需新接口；以 apply 阶段核验 Slack managed 既有路径为基准对齐。

## Risks / Trade-offs

- **[D2 移动 Slack 渲染调用点]** 风险：触及 Slack 审批下发路径。缓解：`approval_prompt_blocks` 输出与 `handle_approval_action` 逐字节不变，仅调用点从 gate 移到 outbound 边界；以全部 Slack 审批单测/集成「无新增失败」为验收闸。
- **[D3 managed 恢复跨进程]** Slack 既有审批按钮在 managed 下的恢复路径本身是既有实现；Telegram 镜像同一中立件与进程局部性，不新增机制；apply 时以 Slack 既有行为为基准核验，不在本 change 重构该机制。
- **[D6 Telegram 文件 API 差异]** Telegram 文件经 bot `get_file` 下载、无 Slack 的 url_private/302/HTML 页特性，故下载实现不照搬 Slack 的重定向/HTML 防御，仅保留大小上限与失败降级——刻意不引入用不到的防御。

## Migration Plan

无数据迁移、无 schema 变更。`permission_gate` 下发由 Slack blocks 改为中立审批意图属行为兼容重构（Slack 渲染输出不变），不留 shim。`reply_func` 签名扩展向后兼容（actions 默认 None）。

## Open Questions

无（brainstorming 锁定方案 B + 去泄漏；managed 恢复细节以 apply 阶段核验 Slack 既有路径为准）。
