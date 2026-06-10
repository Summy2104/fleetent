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
When the agent's final reply for a fired task is exactly the sentinel `[SILENT]`, the system SHALL record the run as successful (`last_status="ok"`) but SHALL NOT deliver any message to the user.

#### Scenario: Silent run delivers nothing
- **WHEN** a fired task's agent reply is exactly `[SILENT]`
- **THEN** no message is sent to any target and the run is recorded as `ok`
