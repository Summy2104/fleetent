# conversation-address-unification

## Why

挂起恢复（approval-suspend-resume）把 run 变成了可跨入口、跨重启续命的持久实体，但 run 的**投递上下文**（往哪个 channel/thread 回话、能否上传文件、progress 回调）仍是入站 handler 手拼的进程内闭包——挂起时不持久化，恢复时由"触发恢复的那条消息"临时重建。2026-06-12 实测：按钮恢复路径重建的 `_reply` 丢 `thread_ts`、`resume_msg` 无 `upload_func`、`SessionContext` 残缺 → 恢复后所有回复（含下一个审批提示）发到顶层脱离原 thread，文件上传通道断失，且错误**链式放大**（第二个审批提示已在顶层，其 payload 再无 thread 可恢复）；thread 锚定的 session id 进一步导致用户在 bot 顶层消息下的追问落进全新会话（trace 实证 `slack:dm:…:1781249557`），任务上下文被切断。文本 `approve` 路径同样继承触发消息的位置——行为取决于用户在哪打字。三个恢复入口（按钮/文本/重启）各拼各的、各缺各的。cron 子系统早已把会话地址建模为持久化数据（`scheduled_tasks.origin`），正确范式存在但 IM 恢复路径未复用。

## What Changes

- **新增 `ConversationAddress` 一等公民**：`{platform, chat_id, target_type, thread_id, user_id}` 数据类。入站时由 adapter 构造一次；**随挂起状态持久化**（session `meta.pending_approvals` 条目内）；与 cron `origin` 描述符同构，内部收敛为同一类型（cron 行为不变）。
- **outbound 投递工厂**：`outbound.make_replier(connectors, address)` / `make_uploader(connectors, address)` 统一构造 reply_func / upload_func（自动带 thread、走既有 `send_to` / `send_file_to` 原语）；入站 handler 与全部恢复入口一律经工厂构造，**删除各处手拼闭包**。
- **恢复上下文等价契约**：三个恢复入口（Slack 按钮、`approve/reject` 文本命令、进程重启后恢复）一律从**持久化 address** 重建投递上下文——恢复后的回复落回原 thread、可上传文件、progress 可用、SessionContext 完整（chat_type/thread_root 不再丢失），与原始入站路径行为等价；附契约回归测试。
- **连带修复**：恢复后审批提示回原 thread → thread 锚定 session 不再分裂；`route()` 收尾的产物外发提示等依赖 reply 上下文的行为在恢复路径同样可用。

## Capabilities

### New Capabilities

- `conversation-address`: 会话地址数据类与持久化、outbound replier/uploader 工厂、恢复入口的投递上下文等价契约。

### Modified Capabilities

- `approval-suspend-resume`: 挂起持久化的 pending 条目增加会话地址；恢复路径的投递上下文 MUST 从持久化地址重建（而非触发消息），按钮/文本/重启三入口行为等价扩展到投递上下文维度。

## Impact

- **代码**：`im_gateway/normalizer.py`（NormalizedMessage 构造、`_resume_pending_in_session`、route 文本 approve 路径）；`im_gateway/slack.py`（`handle_approval_action` 的 `_reply`/`resume_msg`、入站 handler 改用工厂）；`im_gateway/telegram.py`（同构）；`outbound.py`（新增工厂函数）；`runtime/loop.py`（挂起持久化条目增加 address）；`session/manager.py`（pending 条目字段，JSON 兼容旧条目）。
- **owned tables**：无（session meta 为 JSON 文件，旧 pending 条目缺 address 时降级为现状行为并记日志）。
- **config namespace**：无。
- **依赖方向**：im_gateway / runtime → outbound（既有方向），零 platform import。
- **兼容性**：升级前已挂起的 pending 条目无 address → 恢复走现状路径（顶层回复），记 warning；新挂起全部携带。cron `origin` 仅内部类型收敛，spec 行为不变。
- **关联**：与 `unified-file-exchange` 正交（一个管"文件在哪"，一个管"话说给谁"）；`delivery-receipts-postcondition` 的 trailer 经 replier 工厂受益。
