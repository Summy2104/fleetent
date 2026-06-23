## ADDED Requirements

### Requirement: Generate tasks reject embedded send instructions without an explicit target

`schedule_store.create` SHALL reject a `generate` task whose delivery target is **not**
explicitly configured (`deliver is None`) when its `message` contains a send/delivery
imperative directed at a recipient (e.g. 私信 / 发送给 / 发给 / 推送给 / 发到 / send to / DM).
Such a task is the recurring footgun: with no explicit `deliver`, the fired reply falls back to
broadcasting to the creation `origin` (often the wrong place), and the embedded "send to X"
instruction steers the model to self-deliver — together producing mis-routed or duplicate
delivery. The rejection SHALL be a `ValueError` (surfaced by the `schedule` tool as a clean
`error:` text, never an unhandled exception) whose message instructs the author to configure
the delivery target via `notify_target`/`notify_target_type` instead of writing it into
`message`, or to use `task_type="action"` so the agent delivers via its own tools.

The guard SHALL be conservative — it triggers ONLY when all of `task_type == "generate"`,
`deliver is None`, and a send-imperative match hold. A `generate` task with an explicit
`deliver` (delivery is configured) SHALL pass even if its `message` mentions sending; an
`action` task SHALL pass (self-delivery is its purpose); a `generate` task whose `message`
contains no send imperative SHALL pass.

The `schedule` tool's description/parameter guidance (delivered to the model via the tool
schema) SHALL state the principle: the delivery target is configured via `notify_target`
(NOT written into `message`); a `generate` task's reply is delivered by the scheduler (the
model does not self-send), while an `action` task delivers via the agent's own tools.

#### Scenario: Generate + no deliver + send instruction in message is rejected

- **WHEN** `schedule_store.create(task_type="generate", deliver=None, message="把结果私信发送给 U1")`
  is called
- **THEN** it raises `ValueError` whose message tells the author to set `notify_target` or use
  `task_type="action"`, and no task row is created

#### Scenario: Generate with explicit deliver passes

- **WHEN** a `generate` task is created with an explicit `deliver` target, even if its `message`
  mentions sending to someone
- **THEN** creation succeeds (the delivery target is configured)

#### Scenario: Generate with a clean message passes

- **WHEN** a `generate` task with no explicit `deliver` is created whose `message` contains no
  send imperative (e.g. "查询金价并输出正文")
- **THEN** creation succeeds

#### Scenario: Action task with a send instruction passes

- **WHEN** an `action` task is created whose `message` instructs the agent to send to a user
- **THEN** creation succeeds (self-delivery is the purpose of an `action` task)
