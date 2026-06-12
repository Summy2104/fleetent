# conversation-address Delta

## ADDED Requirements

### Requirement: 会话地址为一等持久化数据

系统 SHALL 提供 `ConversationAddress` 数据类 `{platform, chat_id, target_type, thread_id, user_id}`（outbound 顶层基础设施）：入站 IM 消息由 adapter 构造一次；run 因审批挂起时该地址 MUST 随 pending 条目持久化到 session meta；cron `scheduled_tasks.origin` 描述符 MUST 收敛为同一类型解析（fire 投递行为不变）。

#### Scenario: 挂起持久化地址

- **WHEN** 一个 Slack thread 内的 run 因 medium 审批挂起
- **THEN** session meta 的 pending 条目含 `address`（platform=slack、chat_id、thread_id=原 thread、user_id）

#### Scenario: cron origin 同构解析

- **WHEN** 一个含 origin 的定时任务 fire
- **THEN** 投递目标经同一地址类型解析，行为与现状一致（回原 chat/thread）

### Requirement: outbound 投递工厂统一构造投递闭包

系统 SHALL 提供 `outbound.make_replier(connectors, address)` 与 `outbound.make_uploader(connectors, address)`，分别返回携带 thread 的文本回复闭包与文件上传闭包（内部走 `send_to` / `send_file_to` 既有原语与平台分派）。入站 handler 与全部恢复入口 MUST 经工厂构造 reply_func / upload_func，MUST NOT 手拼捕获 channel/thread 的闭包。

#### Scenario: replier 携带 thread

- **WHEN** 用 thread_id 非空的地址构造 replier 并发送文本
- **THEN** 消息投递到该 chat 的对应 thread 内（非顶层）

#### Scenario: uploader 携带 thread

- **WHEN** 用同一地址构造 uploader 并上传文件
- **THEN** 文件作为附件投递到同一 chat/thread

#### Scenario: 平台分派零分支复用

- **WHEN** 地址 platform 为 telegram
- **THEN** 工厂产物经 send_to/send_file_to 的 Telegram 路径投递，工厂自身无平台分支

### Requirement: 恢复入口投递上下文等价

任一恢复入口（Slack 按钮、`approve/reject` 文本命令、进程重启后的恢复）恢复挂起 run 时，SHALL 从持久化 address 重建投递上下文：恢复后的全部输出（含后续审批提示与最终回复）MUST 落回原 chat/thread；upload 能力 MUST 可用且指向同一地址；progress 回调 MUST 可用；持久化的 SessionContext 关键字段（chat_type/thread_root）MUST 还原。文本 approve 命令在哪个位置发出 MUST NOT 影响恢复输出的位置。

#### Scenario: 按钮恢复回原 thread

- **WHEN** 用户点击审批按钮恢复一个原 thread 内挂起的 run
- **THEN** 恢复后的回复与后续审批提示均出现在原 thread 内，而非频道/DM 顶层

#### Scenario: 文本命令位置无关

- **WHEN** 用户在 DM 顶层发送 `approve <id>`，而挂起 run 的地址在某 thread 内
- **THEN** 恢复输出仍落回原 thread

#### Scenario: 恢复后可上传文件

- **WHEN** 恢复后的 run 产生需上传的文件（经上传通道）
- **THEN** 上传到原地址的 chat/thread 成功，upload 通道非缺失

#### Scenario: 重启后恢复等价

- **WHEN** 进程重启后authorized actor 批准一个重启前挂起的审批
- **THEN** 恢复输出仍按持久化地址落回原 chat/thread

### Requirement: 缺失地址的存量 pending 降级不阻塞

升级前已挂起的 pending 条目（无 address 字段）被恢复时，系统 MUST 降级为既有行为（用触发恢复的消息上下文投递）并记录一条 warning，MUST NOT 因缺字段而拒绝或中断恢复。

#### Scenario: 旧条目仍可恢复

- **WHEN** 一个升级前持久化的 pending 条目（无 address）被批准
- **THEN** 恢复正常执行与续跑，输出走触发消息上下文，日志含 missing-address warning
