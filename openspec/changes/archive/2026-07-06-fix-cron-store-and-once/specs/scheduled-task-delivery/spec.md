# scheduled-task-delivery Delta

## ADDED Requirements

### Requirement: Fire failure is proactively reported

当一次 fire 的结果为失败（agent run 抛错，或向解析出的目标投递失败，或 generate 产出非静默回复却无可解析目标）时，调度器 SHALL **best-effort** 向该任务的可解析投递目标（显式 `deliver` 或 `origin`）发送一条简短失败告警（含任务名与错误摘要，如 `⚠️ 定时任务 <name> 执行失败: <error>`）。告警自身的投递失败 SHALL 只记日志——MUST NOT 改变已记录的 fire 结果、MUST NOT 使调度器崩溃。当目标不可解析或 `deliver.mode="none"` 时不发送告警（结果仍如实落 store 与 run history）。为避免告警风暴，recurring 任务连续失败时 SHALL 仅在**失败streak 的首次**（前一次 `last_status` 非 `error`）发送告警；once 任务失败必告警（随即终结）。

#### Scenario: agent run 失败时用户收到告警
- **WHEN** 一个 `generate` 任务 fire 时 agent run 抛错，且任务的 origin 可解析、连接器在线
- **THEN** origin 会话收到一条含任务名与错误摘要的 ⚠️ 告警消息，该次 run 仍记 `error`

#### Scenario: 告警失败不改变 fire 结果
- **WHEN** fire 失败且告警投递也失败（如连接器离线）
- **THEN** 告警失败仅记日志；store 与 run history 中的失败记录不受影响，调度器继续运行

#### Scenario: 连续失败不刷屏
- **WHEN** 一个 recurring 任务连续多次 fire 失败（前次 `last_status` 已为 `error`）
- **THEN** 仅失败 streak 的首次发送告警，后续失败只落 store/history，直到出现一次成功后再次失败才重新告警

## MODIFIED Requirements

### Requirement: Delivery target resolved at fire time
The delivery target SHALL be resolved at fire time, not bound at creation time. Each task SHALL store an `origin` descriptor capturing its creation context (platform, chat_id, optional thread_id) and an optional explicit `deliver` descriptor (`mode` = `origin`/`explicit`/`none`, plus platform/target/target_type/thread for `explicit`). When `deliver` is absent or `mode="origin"`, delivery SHALL go back to the `origin` context. When a task is created via the `schedule` tool from an IM conversation, the `origin` SHALL be auto-captured from the inbound IM context (the tool context's session metadata: platform, channel/chat id, thread); when there is no IM context (e.g. a non-IM caller), `origin` SHALL be absent. **一个 `generate` 任务的 fire 产出非 `[SILENT]` 回复、而投递目标解析为空（origin 缺失且无显式 `deliver`）时，该次 run SHALL 记为 `error`（错误含义 `no_delivery_target`），MUST NOT 记 `ok`——广播型任务的产出无处可去是失败，不是成功；唯一例外是显式 `deliver.mode="none"`（有意不投递），仍记 `ok`。**

#### Scenario: Default delivery to stored origin
- **WHEN** a task with a stored `origin` (platform/chat_id) fires and has no explicit `deliver`
- **THEN** the reply is delivered back to that origin platform/chat/thread

#### Scenario: Origin auto-captured from the creating IM conversation
- **WHEN** a task is created via the `schedule` tool from an IM conversation and no explicit `notify_*` target is given
- **THEN** the task's `origin` is auto-filled from the inbound context (platform, chat id, thread) so a later fire delivers back to that conversation

#### Scenario: No origin captured without IM context
- **WHEN** a task is created via the `schedule` tool with no inbound IM context (no session metadata)
- **THEN** the task is stored with no `origin`, and a fire without an explicit `deliver` performs no delivery

#### Scenario: 无可解析目标的 generate fire 记 error
- **WHEN** 一个无 `origin`、无显式 `deliver` 的 `generate` 任务 fire 并产出非 `[SILENT]` 回复
- **THEN** 该次 run 记 `last_status="error"`（`no_delivery_target`），run history 同步记录；不投递任何消息

#### Scenario: 显式 mode="none" 仍为成功
- **WHEN** 一个 `deliver.mode="none"` 的任务 fire 并产出回复
- **THEN** 不投递且该次 run 记 `ok`（有意不投递是配置行为，非失败）

#### Scenario: Connector resolved at fire time, not creation time
- **WHEN** the IM connector for the target platform was not yet connected when the task was created but is live at fire time
- **THEN** delivery succeeds using the connector resolved at fire time
