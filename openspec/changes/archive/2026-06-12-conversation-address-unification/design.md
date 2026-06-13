# Design — conversation-address-unification

## Context

投递上下文今天的形态：入站 handler（`slack.py` handle_dm 等）拼 `reply_func`（闭包捕获 say/client/channel/`reply_thread = thread_ts or event.ts`）、`upload_func`（`_make_upload_func(client, channel, thread_ts)`）、`SessionContext`，装进 `NormalizedMessage`。挂起时（`loop.py` `state.pending_approvals`）持久化的条目只有 `{approval_id, tool_call_id, tool_name, tool_args, risk, approver_ids}`——**没有任何地址**。恢复时：按钮路径（`slack.py handle_approval_action`）用按钮 payload 的 channel 拼无 thread 的 `_reply`、不装 upload_func、`SessionContext(platform, sender_id)` 两字段；文本路径用 approve 消息自己的上下文；`_resume_pending_in_session` 的 `continue_run` 连 upload_func 参数都没有。对照组：cron 把 `origin={platform, chat_id, target_type, thread_id}` 存表、fire 时经 `outbound.send_to(..., thread=...)` 解析投递——数据驱动范式已存在。

事故时间线证明错误链式放大：第一次按钮恢复丢 thread → 第二个审批提示发顶层 → 其消息 payload 的 thread_ts 为空 → 任何"从触发消息恢复 thread"的补丁只能救第一跳。唯有持久化地址能切断衰减链。

## Goals / Non-Goals

**Goals:**

- 会话地址成为随挂起状态持久化的数据；恢复后的 run 与原始 run 在投递维度**等价**（原 thread、可上传、progress、完整 SessionContext）。
- 所有入口（入站、按钮恢复、文本恢复、重启恢复）经同一对 outbound 工厂构造投递闭包，结构上不可能漏字段。
- 升级兼容：旧 pending 条目（无 address）降级现状行为 + warning，不崩。

**Non-Goals:**

- 投递回执/虚报治理（delivery-receipts-postcondition）；文件平面（unified-file-exchange）；session id 键控策略变更（恢复回原 thread 后分裂自然消失，不动键控规则）；Telegram 之外新平台。

## Decisions

### D1 `ConversationAddress` 数据类，与 cron origin 同构收敛

`{platform, chat_id, target_type, thread_id, user_id}` frozen dataclass，放 `outbound.py`（顶层基础设施，im_gateway 与 runtime 都已依赖它，不引入新方向）。cron 的 origin dict 解析点改为构造同一类型（行为不变）。备选：放 normalizer——会让 runtime/loop 反向 import im_gateway 内部，否决。

### D2 持久化位置 = pending 条目内嵌

挂起时 `state.pending_approvals` 条目增加 `address` 字段（dataclass→dict 序列化），随既有 `session_mgr.add_pending_approval` 落 session meta。备选：session meta 顶层单独存——一个 session 可能有多个 pending（不同轮次），条目内嵌天然随条目生命周期清理。

### D3 工厂签名与去闭包

```
outbound.make_replier(connectors, address)  -> reply_func(text, blocks=None)
outbound.make_uploader(connectors, address) -> upload_func(paths)
```

内部走 `send_to` / `send_file_to`（均已支持 thread/target_type）。入站 handler 改造为：构造 address → 工厂得 reply/upload → 装 NormalizedMessage（say 优先路径保留给入站性能/语义不变时，等价性测试兜底）。恢复入口一律：读 pending 条目 address → 工厂重建 → `_resume_pending_in_session`（其 `continue_run` 增加 upload_func 透传）。SessionContext 在挂起时一并持久化关键字段（chat_type/thread_root/channel_name），恢复时还原。

### D4 三入口等价契约测试

一组 integration 契约测试参数化三个恢复入口（按钮 / 文本 / 重启模拟），断言：恢复后 reply 携带原 thread_ts；upload_func 非 None 且指向原 channel+thread；progress 可用；SessionContext.chat_type 保真。任何后续新增入口必须进该参数化集（防回归的结构性保障）。

### D5 降级语义

pending 条目无 address（升级前挂起的存量）→ 恢复路径回退现状行为（触发者上下文），记 `approval_resume_missing_address` warning。不阻塞恢复——决策优先于体验。

## Risks / Trade-offs

- [按钮 payload 与持久化 address 不一致（极端：频道被归档）] → 投递失败走 send_to 既有 best-effort 语义，错误回文本提示。
- [SessionContext 持久化引入 PII（sender_name）] → 只持久化路由必需字段（platform/chat/thread/user_id/chat_type），名称类字段恢复时留空。
- [双平台（Slack/Telegram）工厂分派差异] → 复用 send_to 的平台分派，工厂零平台分支。
- [旧条目降级路径长期存活] → 该路径只服务升级窗口内的存量 pending，approvals 有超时机制自然排干。

## Migration Plan

部署即生效；存量 pending 走降级路径并随审批超时自然清空。回滚：去掉 address 字段读取即回现状（字段冗余无害）。

## Open Questions

- 无。
