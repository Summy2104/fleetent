## REMOVED Requirements

### Requirement: Isolated playground session
**Reason**: Playground 在 platform 进程内直接调用 `run_stream`，违反 platform-control-plane 边界（platform 不得执行 agent loop）。整个 chat-playground capability 随本 change 下线。
**Migration**: 使用 TUI（`fleetent-tui`）或 IM 渠道（Slack/Telegram）测试 agent 对话；admin 控制台不再内嵌试验场。

#### Scenario: Start playground session for an agent

- **WHEN** an admin selects Agent "ops-bot" in the playground and sends a trial message
- **THEN** a session marked `origin=playground` is created, associated only with the admin, not bound to any real user or channel

#### Scenario: Playground excluded from external usage

- **WHEN** a playground message completes for "ops-bot"
- **THEN** its tokens and call are NOT counted toward "ops-bot" external usage statistics

#### Scenario: Discardable

- **WHEN** an admin abandons an unpinned playground session
- **THEN** it may be discarded and is removed by retention cleanup after the retention period

### Requirement: Streaming reply with per-turn observability
**Reason**: 同上，整个 capability 随 playground 下线。
**Migration**: 同上。

#### Scenario: SSE stream with observability panel

- **WHEN** an admin sends a playground message to "ops-bot"
- **THEN** the reply streams over SSE, and the side panel shows the turn's injected Skill / KB recall, tool call inputs/outputs, approval decision, and model routing

### Requirement: Per-request parameter overrides
**Reason**: 同上。
**Migration**: 同上。

#### Scenario: Override model and disable a Skill for this session only

- **WHEN** an admin overrides the model to a cheap model and disables a Skill, then chats in that playground session
- **THEN** the session runs with the overridden model and reduced Skill set; the Agent's persistent config is unchanged and other sessions are unaffected

### Requirement: Controlled approval bypass (playground only)
**Reason**: 同上。
**Migration**: 同上。

#### Scenario: Bypass does not affect real sessions

- **WHEN** an admin enables "auto-approve medium risk" on their playground session and a medium-risk tool fires, while a real user session simultaneously fires a medium-risk tool
- **THEN** the playground session auto-approves and writes an audit entry; the real user session still enters permission_gate and waits for approval — the bypass does not reach it

#### Scenario: High risk still confirmed

- **WHEN** a playground session with the bypass enabled fires a high-risk tool
- **THEN** the tool still requires explicit confirmation; the bypass does not cover high risk

### Requirement: Playground retention, pinning, and export
**Reason**: 同上。
**Migration**: 同上。

#### Scenario: Pin to retain

- **WHEN** an admin pins a playground session with a note
- **THEN** the session is exempt from retention cleanup until unpinned

#### Scenario: Export playground session

- **WHEN** an admin exports a playground session
- **THEN** a JSON / Markdown artifact is produced and the export is audited

#### Scenario: Unpinned cleanup

- **WHEN** an unpinned playground session exceeds the retention period
- **THEN** it is removed by retention cleanup
