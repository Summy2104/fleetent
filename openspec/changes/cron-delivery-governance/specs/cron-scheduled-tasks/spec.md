# cron-scheduled-tasks Delta

## ADDED Requirements

### Requirement: Create-time delivery-target resolvability for broadcast tasks

`schedule_store.create` SHALL reject（`ValueError`）一个 `generate` 任务，当其**既无显式 `deliver` 又无 `origin`**——广播型任务的产出必须有处可去；唯一例外是显式 `deliver.mode="none"`（有意不投递）。该校验镜像既有 notify 校验（notify 已要求 deliver 或 origin 之一）。`action` 任务不受此校验（其投递经自身工具完成）。`schedule` 工具 SHALL 将该 `ValueError` 转为干净的 `error:` 文本并附配置指引（提供 `notify_platform`+`notify_target`，或改用 `task_type="action"`），不向 agent loop 抛未处理异常。

#### Scenario: 无目标 generate 在创建时被拒
- **WHEN** `schedule_store.create(task_type="generate", deliver=None, origin=None, message="每日汇总")` 被调用
- **THEN** 抛出 `ValueError`（指引配置 notify_target 或改用 action），不落任何行

#### Scenario: 显式 mode="none" 放行
- **WHEN** 一个 `generate` 任务以 `deliver={"mode": "none"}`、无 `origin` 创建
- **THEN** 创建成功（有意不投递是合法配置）

#### Scenario: 有 origin 的 generate 照常创建
- **WHEN** 一个 `generate` 任务从 IM 会话创建（origin 自动捕获）、无显式 deliver
- **THEN** 创建成功，投递回落 origin（既有行为不变）

#### Scenario: action 不受目标校验
- **WHEN** 一个 `action` 任务以无 deliver、无 origin 创建
- **THEN** 创建成功（action 经自身工具投递，不需要调度器目标）

## MODIFIED Requirements

### Requirement: schedule tool for managing scheduled tasks

A single `schedule` built-in tool SHALL let an agent manage scheduled tasks via an `action` parameter (`create`, `list`, `remove`, `run_now`, `pause`, `resume`). It SHALL have `risk_level="low"` and SHALL NOT require human approval. The tool SHALL perform all mutations through the running `CronScheduler` instance obtained via `cron_scheduler.current()` — never by writing `schedule_store` directly. `create` SHALL accept `task_type` (default `generate`) and `notify_text`, enforcing the per-type validation (notify requires `notify_text` + delivery target; generate/action require `message`) and returning a clean error string rather than raising on a validation failure; its tool description SHALL carry the type-deciding question ("does the message content need information only known at send time?") plus the creation-time finalize-and-confirm flow for notify copy. `create` SHALL stamp the task's owner from the execution principal (`tool_context.principal.user_id`) when available, falling back to the `user_id` parameter only when no principal is present — the model-supplied parameter MUST NOT override an available principal. `create` SHALL return the new task's id; `pause`/`resume` SHALL toggle the task's `enabled` flag and deregister/register the APScheduler job accordingly; `run_now` SHALL fire the task immediately via a public scheduler method. When no scheduler is running (one-shot CLI run, or `scheduling.enabled=false`), mutations SHALL still persist to the store and the tool result SHALL state truthfully that the task takes effect when the agent service is running — the tool MUST NOT report the task as active.

**投递目标参数 SHALL 成对提供**：`notify_platform` 与 `notify_target` 只提供其一时，`create` SHALL 返回明确的 error 文本（指出缺失的参数），MUST NOT 静默忽略并回落 origin。**create 成功回执 SHALL 明示最终投递目标**：显式目标写成 `platform:target(target_type)` 形式；无显式目标时写明「投递回创建会话（origin）」——使目标错配在创建当下即对用户可见。

The `schedule` tool's parameter contract SHALL be carried in the **tool schema delivered to the model** (the model receives the schema, not the Python function's docstring body): `action`, `schedule_kind`, `task_type`, and `notify_target_type` SHALL be declared as enumerated parameters (via `Literal`) so the model receives their allowed values, and every parameter SHALL carry a description (via `Annotated`) so per-parameter guidance reaches the model. Because `schedule_kind` is enumerated, the model cannot emit a non-member value such as `run_at` (the forgiving normalization underneath remains for non-model callers). The `task_type` parameter description SHALL convey the notify/generate/action selection rule and the default `generate`. **`notify_platform`/`notify_target` 的参数描述 SHALL 说明二者须成对提供。**

The `timezone` parameter SHALL default to unspecified (empty), NOT to a hardcoded `"UTC"`; when the model does not supply a timezone, `create` SHALL pass it through as absent (`None`) so the deployment-default resolution applies (see "Timezone resolution is local-clock and DST-safe"). The `timezone` and `cron_expr` parameter descriptions SHALL state that cron fields are the **local wall-clock time of the task timezone** and MUST NOT be pre-converted to UTC, and that an unspecified timezone uses the deployment default while an explicit timezone is set only when the user names one. On a successful `create`, the tool result SHALL state the task's next fire time in **both the task timezone and UTC**.

#### Scenario: Agent creates a notify task with frozen copy
- **WHEN** an agent calls `schedule(action="create", task_type="notify", notify_text="📅 晨会提醒：9:00 准时开始", schedule_kind="cron", cron_expr="0 9 * * 1-5")`
- **THEN** the task is created with `task_type="notify"`, fires agent-free, and its id is returned

#### Scenario: Notify creation without copy is rejected
- **WHEN** an agent calls `schedule(action="create", task_type="notify")` without `notify_text`
- **THEN** the tool returns a validation error string without raising

#### Scenario: half-set 投递参数被拒
- **WHEN** an agent calls `schedule(action="create", notify_target="C123", ...)`（提供了 `notify_target` 但缺 `notify_platform`，或反之）
- **THEN** the tool returns 明确 error 文本指出须成对提供，不创建任务、不静默回落 origin

#### Scenario: 回执明示显式投递目标
- **WHEN** a task is created with `notify_platform="slack"`, `notify_target="C123"`, `notify_target_type="channel"`
- **THEN** the create 回执含 `slack:C123(channel)` 字样，用户可当场发现目标错配

#### Scenario: 回执明示 origin 回落
- **WHEN** a task is created from an IM conversation with no explicit target
- **THEN** the create 回执写明投递将回到创建会话（origin）

#### Scenario: Agent creates a schedule without approval
- **WHEN** an agent calls `schedule(action="create", schedule_kind="cron", cron_expr=..., message=...)` while the scheduler is running
- **THEN** a task is created with `source="tool"`, its APScheduler job is registered immediately (fires on time with no restart), and its id is returned — with no approval gate

#### Scenario: Agent pauses and resumes a schedule
- **WHEN** an agent calls `schedule(action="pause", task_id=...)` then later `schedule(action="resume", task_id=...)`
- **THEN** the task's `enabled` flag is set to false then true, and the APScheduler job is deregistered then re-registered

#### Scenario: Agent removes a schedule
- **WHEN** an agent calls `schedule(action="remove", task_id=...)` with a valid id
- **THEN** the task is deleted from `scheduled_tasks` and deregistered from the scheduler

#### Scenario: run_now fires immediately
- **WHEN** an agent calls `schedule(action="run_now", task_id=...)`
- **THEN** the task fires once immediately via the scheduler's public API without altering its normal schedule

#### Scenario: Removing non-existent task returns error message
- **WHEN** an agent calls `schedule(action="remove", task_id="nonexistent")`
- **THEN** the tool returns an error string without raising an exception

#### Scenario: Create without a running scheduler degrades honestly
- **WHEN** an agent calls `schedule(action="create", ...)` and `cron_scheduler.current()` is None
- **THEN** the task is persisted to the store and the tool result states it will take effect when the agent service is running, not that it is active now

#### Scenario: Task owner comes from the execution principal
- **WHEN** an agent calls `schedule(action="create", user_id="whatever-the-model-typed")` with a `tool_context` carrying a resolved principal
- **THEN** the created task's `user_id` is the principal's `user_id`, not the model-supplied parameter

#### Scenario: Model receives task_type and schedule_kind enums in the schema
- **WHEN** the `schedule` tool schema is built by the schema builder and delivered to the model
- **THEN** the `task_type` parameter exposes the enum `["notify", "generate", "action"]` with a description conveying the selection rule, and the `schedule_kind` parameter exposes the enum `["cron", "once", "interval"]`

#### Scenario: timezone parameter carries the no-pre-convert contract
- **WHEN** the `schedule` tool schema is built
- **THEN** the `timezone` (and `cron_expr`) parameter descriptions state that cron fields are the task timezone's local wall-clock time and MUST NOT be pre-converted to UTC, and that an unspecified timezone uses the deployment default

#### Scenario: Unspecified timezone is passed through, not forced to UTC
- **WHEN** an agent calls `schedule(action="create", schedule_kind="cron", cron_expr="0 18 * * *", message=...)` with no `timezone`
- **THEN** the persisted task does not carry a hardcoded `"UTC"` that defeats the fallback, and the scheduler resolves the effective timezone from `agent.scheduling.default_timezone`

#### Scenario: Create result states the next fire time in task timezone and UTC
- **WHEN** an agent creates a cron task on a running scheduler
- **THEN** the tool result states the next fire time in both the task timezone and UTC, and the task's `next_run_at` is populated

### Requirement: Cron trigger fires agent run asynchronously

When a scheduled task becomes due (its persisted `next_run_at <= now` on a tick), the scheduler SHALL fire **according to the task's `task_type`**: `notify` sends `notify_text` verbatim via the fire-time connector snapshot **without invoking `agent_loop.run`**; `generate` and `action` call `agent_loop.run()` with the task's `message`, `user_id`, resolved agent context, and the fire-time `outbound_connectors` snapshot. For `generate`, the run additionally receives the scheduled-run delivery statement AND is invoked with outbound-tool suppression (`suppress_outbound_tools=True`) so the run produces only the notification body and the scheduler performs the sole delivery (`send_im_message`/`send_file` are absent from a generate run's tool schema). For `action`, the run retains the outbound tools (so the agent delivers via its own tools and the scheduler does not broadcast). **无论 `generate` 还是 `action`，fired run 的工具 schema SHALL 排除 `schedule` 工具**——定时触发的运行 MUST NOT 能创建、修改或删除定时任务（防自我增殖；任务管理属交互式会话）。The fire SHALL NOT block the tick loop (the run is dispatched so the loop keeps selecting and advancing other due tasks), and the run result SHALL be recorded in the observability trace AND as a run-history row (see capability `cron-run-history`). `last_status` SHALL reflect the **task intent** outcome per type — notify: delivery outcome; generate: run + delivery outcome; action: run outcome — never merely "the delivery API call succeeded". A due occurrence SHALL NOT be silently dropped: an occurrence that cannot run (e.g. its owner is skipped/unverified) SHALL be recorded as a `skipped` run rather than vanishing without a trace.

#### Scenario: Notify fire bypasses the agent
- **WHEN** a `notify` task becomes due
- **THEN** the scheduler sends `notify_text` to the resolved target without calling `agent_loop.run`

#### Scenario: Agent run triggered on schedule
- **WHEN** a `generate` or `action` task becomes due
- **THEN** `agent_loop.run()` is invoked with the task's message and user_id without blocking the tick loop

#### Scenario: Action fire can deliver via IM tools
- **WHEN** an `action` task fires whose message asks the agent to send a message/notification to a channel or user
- **THEN** the agent run receives the fire-time `outbound_connectors` snapshot AND retains the outbound tools, so an outbound IM tool invoked inside the run reaches the live connector (the run is not told "no connector available")

#### Scenario: Generate fire produces content but does not self-deliver
- **WHEN** a `generate` task fires
- **THEN** `agent_loop.run()` is invoked with `suppress_outbound_tools=True` so `send_im_message`/`send_file` are absent from the run's schema, and the final reply is delivered solely by the scheduler's broadcast

#### Scenario: fired run 不能再造定时任务
- **WHEN** 一个 `action`（或 `generate`）任务 fire，其 message 诱导 agent 调用 `schedule(action="create", ...)`
- **THEN** fired run 的工具 schema 中不存在 `schedule` 工具，无法创建新定时任务；交互式会话中的 `schedule` 工具不受影响

#### Scenario: No connectors available degrades cleanly
- **WHEN** a task fires while no IM connector is registered for the agent
- **THEN** `agent_loop.run()` receives an empty `outbound_connectors` mapping and the run proceeds without error

#### Scenario: Run outcome recorded in runtime-state columns and history
- **WHEN** a triggered agent run completes or fails
- **THEN** the task's `last_run_at`, `last_status`, and (on failure) `last_error` are updated, a run-history row is appended, and the run is written to the eval trace

#### Scenario: Unrunnable due occurrence is recorded as skipped
- **WHEN** a task becomes due but its fire-time principal cannot be verified (owner blocked/vanished) so it does not run
- **THEN** a `skipped` run-history row is recorded (the occurrence is not silently dropped)
