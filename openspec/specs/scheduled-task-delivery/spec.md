# scheduled-task-delivery Specification

## Purpose
Proactive delivery of a fired scheduled task's reply to a resolved IM target — the explicit `deliver` descriptor or, by default, the creation `origin` (auto-captured from the IM context) — using the agent's own live connectors, best-effort and `[SILENT]`-suppressible.

## Requirements

### Requirement: Fired task output delivered to the user
When a scheduled task fires, the system SHALL run the agent and then proactively deliver the agent's final reply to a resolved IM target, so the user receives the reminder without polling. Delivery SHALL use the agent's own live IM connectors (no platform dependency) and SHALL be best-effort: a delivery failure SHALL be recorded (`last_error`/`last_status`) and MUST NOT crash the fire.

#### Scenario: Reminder delivered after fire
- **WHEN** a scheduled task fires and the agent produces a reply
- **THEN** the reply text is sent to the resolved target via the agent's live connector for that platform

#### Scenario: Delivery failure does not crash the fire
- **WHEN** delivery to the resolved target fails (e.g. network or unknown target)
- **THEN** the failure is recorded on the task and the fire completes without raising

### Requirement: Delivery target resolved at fire time
The delivery target SHALL be resolved at fire time, not bound at creation time. Each task SHALL store an `origin` descriptor capturing its creation context (platform, chat_id, optional thread_id) and an optional explicit `deliver` descriptor (`mode` = `origin`/`explicit`/`none`, plus platform/target/target_type/thread for `explicit`). When `deliver` is absent or `mode="origin"`, delivery SHALL go back to the `origin` context. When a task is created via the `schedule` tool from an IM conversation, the `origin` SHALL be auto-captured from the inbound IM context (the tool context's session metadata: platform, channel/chat id, thread); when there is no IM context (e.g. a non-IM caller), `origin` SHALL be absent.

#### Scenario: Default delivery to stored origin
- **WHEN** a task with a stored `origin` (platform/chat_id) fires and has no explicit `deliver`
- **THEN** the reply is delivered back to that origin platform/chat/thread

#### Scenario: Origin auto-captured from the creating IM conversation
- **WHEN** a task is created via the `schedule` tool from an IM conversation and no explicit `notify_*` target is given
- **THEN** the task's `origin` is auto-filled from the inbound context (platform, chat id, thread) so a later fire delivers back to that conversation

#### Scenario: No origin captured without IM context
- **WHEN** a task is created via the `schedule` tool with no inbound IM context (no session metadata)
- **THEN** the task is stored with no `origin`, and a fire without an explicit `deliver` performs no delivery

#### Scenario: Connector resolved at fire time, not creation time
- **WHEN** the IM connector for the target platform was not yet connected when the task was created but is live at fire time
- **THEN** delivery succeeds using the connector resolved at fire time

### Requirement: Explicit delivery override
A task SHALL support an explicit delivery target overriding `origin`: a platform (`slack`/`telegram`), a target id, and a `target_type` (`user` for DM or `channel` for a channel/group), with optional thread. The fire path SHALL deliver to a channel via the platform's channel-post path and to a user via DM accordingly.

#### Scenario: Deliver to an explicit channel
- **WHEN** a task has `deliver` with `mode="explicit"`, `platform="slack"`, `target_type="channel"`, `target="C123"`
- **THEN** the fired reply is posted to Slack channel `C123` rather than the creator's DM

#### Scenario: Deliver on a different platform
- **WHEN** a task created from Slack specifies `deliver` with `platform="telegram"` and a Telegram target
- **THEN** the fired reply is delivered via the agent's Telegram connector

### Requirement: SILENT reply suppresses delivery

When the agent's final reply for a fired task is the sentinel `[SILENT]`, the system SHALL record the run as successful (`last_status="ok"`) but SHALL NOT deliver any message to the user.

触发任务的 run 输出 MUST NOT 携带面向操作者的投递回执 trailer(`📬 实际投递…`):该回执是为**交互式对话**确认投递而设计的,定时任务在触发时无交互对象,其回复是要广播的通知正文。因此 fired-run 的回执 trailer SHALL 被抑制,使广播正文与 `[SILENT]` 哨兵保持干净(不含操作者向说明)。

静默判定 SHALL 对尾随内容(回执 trailer、空白等)鲁棒:当回复的首个非空行 strip 后等于 `[SILENT]`(或回复为 None / 空白)时,即视为静默并跳过投递——即使其后被追加了其它内容,也不得因此把哨兵广播出去。IM 交互路径(非定时任务)的投递回执不受影响。

#### Scenario: Silent run delivers nothing
- **WHEN** a fired task's agent reply is `[SILENT]`
- **THEN** the run is recorded ok and no message is delivered to the user

#### Scenario: 带回执的静默回复仍跳过投递
- **WHEN** fired-run 内发生过投递(台账非空),若 run 未抑制回执则回复会变成 `[SILENT]\n\n📬 实际投递：消息 1（U0…）`
- **THEN** 投递判定仍将其识别为静默(首行 == `[SILENT]`)并跳过,绝不把 `[SILENT]` 或回执广播给用户

#### Scenario: fired-run 广播正文不含操作者回执
- **WHEN** 一个非静默的 fired task 在 run 内调用了 send_im_message/send_file（台账非空），最终回复为通知正文
- **THEN** 广播到目标的内容为干净的通知正文,MUST NOT 追加 `📬 实际投递…` 操作者回执

#### Scenario: 交互式 IM 投递回执不受影响
- **WHEN** 普通(非定时任务)IM 对话中 agent 调用 send_im_message/send_file 并投递成功
- **THEN** 该交互回复照常携带 `📬 实际投递…` 回执(默认行为不变)
