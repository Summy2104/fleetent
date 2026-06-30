# telegram-slack-parity

## Why

Telegram 集成约 60% 完整：入站文本/图片、出站文本/文件、typing 心跳、per-agent 绑定、ImAccess、node 托管、身份解析都已具备，但相对 Slack 仍有三处**真实**能力缺口（已用代码核实，并排除两处伪缺口）：

- **审批按钮**：`permission_gate` 经 `reply_func`/`send_to` 下发审批提示，`approval_prompt_blocks` 仅产 Slack Block Kit；Telegram 的 `_telegram_send`/`reply_func` 丢弃 `blocks`，审批者只见文本、点击无 `CallbackQueryHandler` 承接。Telegram 上需审批的中/高风险动作只能走文本指令、无法点按钮批准。
- **非图片文件入站**：Slack `_download_attachments` 把非图片下成 `FileAttachment`（大小上限 + 占位降级）；Telegram handler 仅 `filters.PHOTO`，文档/任意文件收不到。
- **生成图片/文件自动回投**：Slack 入站设 `upload_func`（→ `outbound.send_file_to`），agent 产出的图片自动投回原会话；Telegram 入站未设 `upload_func`，`generate_image` 等产物不会自动投递。

**排除的伪缺口**：slash command（Slack 自身也无 `app.command`，Telegram 过滤命令属对等）；clarify 选择题按钮（`render_clarify_slack/telegram` 仅被单测引用、生产无人调用，两端皆死代码；clarify 实走 `user_input_gate` 文本回答，Telegram 已对等）。

## What Changes

补齐上述三块，使 Telegram 与 Slack 能力矩阵一致。采用**方案 B（按平台各自渲染）+ governance 去泄漏**，对 Slack 行为零改动：

- **governance 去泄漏（对齐既有 spec 意图）**：`permission-gate` spec 早已要求"gate 不透明地传递交互 payload、不知平台渲染细节"，但实现里 `permission_gate` 直接 `import approval_prompt_blocks` 构造 Slack 形状 blocks——本 change 让 gate 改发**平台无关的审批意图**（`approval_id` + 固定动作集 approve/reject/approve_always + summary），渲染下沉到 outbound 边界按平台分发：Slack → `approval_prompt_blocks`（输出逐字节不变），Telegram → 新 `render_approval_telegram`（`InlineKeyboardMarkup`，`callback_data` 编码 `approval_id`+`decision`）。
- **Telegram 审批入站**：`im_gateway/telegram.py` 注册 `CallbackQueryHandler(approval_*)`，镜像 `slack.handle_approval_action`——复用既有中立件 `approval_router.resolve_approval_request` + `session_mgr.get_pending_approval`（授权校验）+ `normalizer._resume_pending_in_session`（恢复挂起 run）；点击后 `edit_message_text` 去键盘防重复点，非授权点击 `callback.answer(alert)` 提示。
- **Telegram `reply_func` 支持按钮**：从 `(text)` 扩成 `(text, 可选交互动作)`，会话内审批提示也出按钮（对标 Slack `reply_func(text, blocks)`）。
- **非图片文件入站**：handler filter 加 `filters.Document`（保留 `PHOTO` 视觉路径）；新增 `_download_document_attachments` 镜像 Slack `_download_attachments`（大小上限、失败/超限降级 `data=None` 占位 `FileAttachment`）。
- **生成图片自动回投**：Telegram 入站 `NormalizedMessage` 设 `upload_func`，镜像 `slack._make_upload_func` → `outbound.send_file_to`（复用 `ConversationAddress`）。
- **托管模式**：回调在 supervisor 宿主（managed=node）的 polling Application 上承接，复用同批中立件，与 Slack 同构（node 持连接、调中立 store/resume），无需新接口。

## Impact

- **影响 capability**：
  - MODIFIED `per-agent-telegram-connector`（入站加 document filter + 审批 callback 承接 + upload_func 接线）
  - MODIFIED `permission-gate`（审批提示交互动作：gate 发中立意图、outbound 边界按平台渲染；Telegram 成为支持交互的渠道）
  - ADDED to `im-file-attachment`（Telegram 适配器下载非图片文件为文件附件项）
  - ADDED to `im-generated-image-upload`（Telegram 适配器上传生成图片到原会话）
- **对 Slack 零行为改动（硬目标）**：`approval_prompt_blocks` 输出与 `slack.handle_approval_action` 不改，仅移动 Slack 渲染的调用点到 outbound 边界；门禁含全部 Slack 单测/集成，判据为无新增失败。

### 模块边界影响（实现前声明）

- **owning packages**：`im_gateway/telegram.py`（入站 filter + 审批 callback + `reply_func` 按钮 + `upload_func`）；`outbound.py`（新增 `render_approval_telegram` + 发送边界按平台分发 + `_telegram_send` 支持 keyboard）；`governance/permission_gate.py`（去泄漏：发中立审批意图）。`im_gateway/clarify_renderer.py` 不动。
- **public API surface**：`outbound` 新增 `render_approval_telegram`、审批意图渲染分发；`permission_gate` 内部下发改为中立意图（对调用方无新增公共参数，Slack 输出不变）；`telegram.reply_func` 签名扩展（向后兼容默认无按钮）。
- **owned tables**：无。
- **config namespace**：无（沿用 `im.telegram` 的 `TelegramBinding`/`ImAccess`）。
- **cross-module dependencies**：全部 agent 侧 edge，MUST NOT `import fleetent.platform`；复用既有中立审批件（`governance.approval_router`/`session.manager`/`runtime` 经 `normalizer._resume_pending_in_session`）；node `im_edge` 已托管 `TelegramSupervisor`，回调随 polling 连接生效。
- **migration / shim plan**：无数据迁移。`permission_gate` 下发接口由"传 Slack blocks"改为"传中立审批意图"——Slack 渲染输出不变、仅调用点移动，须保证 Slack 审批单测/集成全绿（视为行为兼容，不留 shim）。

### 范围 / 非目标（YAGNI）

做：Telegram 审批按钮（两态）、非图片文件入站、生成图片/文件自动回投、governance 审批意图去泄漏。
不做（后续）：slash command（Slack 也无）、clarify 按钮（死代码）、富 Block Kit 排版对齐、WhatsApp 渲染。
