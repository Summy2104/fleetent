# chat-playground Specification

## Purpose
TBD - created by archiving change 2026-06-02-chat-management. Update Purpose after archive.
## Requirements
### Requirement: Isolated playground session

An admin SHALL be able to select any enabled Agent and start an isolated trial session marked `origin=playground`. The session SHALL NOT count toward the Agent's external usage statistics and SHALL NOT be bound to any real user or channel.

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

Playground messages SHALL stream the reply over SSE (same semantics as `/chat`) and SHALL expose per-turn observable detail: injected system prompt / Skill / knowledge-base recall snippets, each tool call's inputs and outputs, permission_gate decisions, model routing and fallback, token and latency.

#### Scenario: SSE stream with observability panel

- **WHEN** an admin sends a playground message to "ops-bot"
- **THEN** the reply streams over SSE, and the side panel shows the turn's injected Skill / KB recall, tool call inputs/outputs, approval decision, and model routing

### Requirement: Per-request parameter overrides

The playground SHALL allow temporarily overriding the current session's task_type / model / temperature / which Skills / knowledge bases are enabled. Overrides SHALL apply only to the current playground session and SHALL NOT change the Agent's persistent configuration or affect other sessions.

#### Scenario: Override model and disable a Skill for this session only

- **WHEN** an admin overrides the model to a cheap model and disables a Skill, then chats in that playground session
- **THEN** the session runs with the overridden model and reduced Skill set; the Agent's persistent config is unchanged and other sessions are unaffected

### Requirement: Controlled approval bypass (playground only)

An admin MAY enable "auto-approve medium risk" for their own playground session. The bypass SHALL apply only to `origin=playground` sessions, SHALL still require explicit confirmation for high risk, SHALL write an audit entry on each auto-approval, and SHALL NOT affect real user sessions.

#### Scenario: Bypass does not affect real sessions

- **WHEN** an admin enables "auto-approve medium risk" on their playground session and a medium-risk tool fires, while a real user session simultaneously fires a medium-risk tool
- **THEN** the playground session auto-approves and writes an audit entry; the real user session still enters permission_gate and waits for approval — the bypass does not reach it

#### Scenario: High risk still confirmed

- **WHEN** a playground session with the bypass enabled fires a high-risk tool
- **THEN** the tool still requires explicit confirmation; the bypass does not cover high risk

### Requirement: Playground retention, pinning, and export

The playground SHALL allow pinning a session with a note (exempting it from retention cleanup) and exporting a session as JSON / Markdown for regression comparison. Export SHALL be audited. Unpinned playground sessions SHALL be cleaned up after the retention period.

#### Scenario: Pin to retain

- **WHEN** an admin pins a playground session with a note
- **THEN** the session is exempt from retention cleanup until unpinned

#### Scenario: Export playground session

- **WHEN** an admin exports a playground session
- **THEN** a JSON / Markdown artifact is produced and the export is audited

#### Scenario: Unpinned cleanup

- **WHEN** an unpinned playground session exceeds the retention period
- **THEN** it is removed by retention cleanup

