# session-admin-console Specification

## Purpose
TBD - created by archiving change 2026-06-02-chat-management. Update Purpose after archive.
## Requirements
### Requirement: Session list and search

The console SHALL list all real sessions (web + IM, excluding `origin=playground`) with filtering and sorting by user / Agent / channel / platform / time / keyword / status (active / idle / ended). Each row SHALL show the originating user, owning Agent, source channel, turn count, last activity, token usage, and whether it has pending approvals.

#### Scenario: Filter real sessions

- **WHEN** an admin or viewer filters sessions by user, Agent, channel, time, keyword, or status
- **THEN** matching real sessions are returned with originating user, Agent, channel, turn count, last activity, token usage, and pending-approval flag; playground sessions are not listed

### Requirement: Per-turn replay reuses read-only browsing

The console SHALL render a single session's full transcript and per-turn tool calls, permission_gate decisions, model routing, and memory / KB hits by reusing the read-only "session & trace browsing" capability, overlaying write-operation entry points on top.

#### Scenario: Open session detail

- **WHEN** an admin opens a single session
- **THEN** the full transcript and per-turn observability are shown (read-only reuse) with write-operation entry points overlaid

### Requirement: Session takeover with human injection

An admin SHALL be able to take over an active session, pausing the agent's automatic replies, and inject a message as a human. For IM sessions the message SHALL be delivered back to the user's original platform via im-gateway. Takeover and release SHALL be audited and the end user SHALL be marked "handed to human / restored to automatic".

#### Scenario: Take over an IM session and inject

- **WHEN** Alice's IM session is active and an admin clicks "take over", pausing automatic replies, and injects a message
- **THEN** the message is delivered back to Alice's platform via im-gateway, the agent does not reply automatically during takeover, both takeover and release are audited, and releasing restores automatic replies

### Requirement: Force-end / clear / reset

An admin SHALL be able to force-end a session (no longer accepting new turns), clear a session's context (equivalent to im-gateway `/new`, executed by the session domain), or reset it to before a given turn. These high-risk actions SHALL require a second confirmation and SHALL be audited.

#### Scenario: Force-clear session context

- **WHEN** a session's context is abnormal and an admin clicks "clear" and confirms
- **THEN** the session domain clears the context (equivalent to `/new`), the session continues from empty context, and the clear action is audited

#### Scenario: Force-end stops new turns

- **WHEN** an admin force-ends a session and confirms
- **THEN** the session status becomes `ended`, no longer accepts new turns, and the action is audited

### Requirement: Batch disposal and quota linkage

The console SHALL allow batch ending / clearing of abnormal sessions by filter result, auditing each with a shared batch id, and SHALL show per-session token usage linked to the usage & quota capability to locate sessions with abnormal usage spikes.

#### Scenario: Batch clear by filter

- **WHEN** an admin batch-clears sessions matching a filter
- **THEN** each session is cleared, audited individually with a shared batch id, and token usage is shown linked to quota

### Requirement: Export with audit trail

The console SHALL allow exporting a single session or batch of sessions' transcripts as JSON / Markdown. Export SHALL be audited; exports containing personal data MAY require a second confirmation or redaction per deployment policy.

#### Scenario: Export session transcript

- **WHEN** an admin exports a session transcript
- **THEN** a JSON / Markdown artifact is produced and the export is audited

### Requirement: Chat management permissions and audit

Playground trials and session takeover / injection / force-end / clear / reset / export SHALL be admin-only. Viewers SHALL be limited to read-only browsing and replay. High-risk actions SHALL require a second confirmation, and all write operations SHALL be audited (who / when / which session / what).

#### Scenario: Viewer is read-only

- **WHEN** a viewer opens chat and attempts to start a playground trial or take over / clear a session
- **THEN** the action's button is hidden or returns 403; the viewer can only browse the session list and per-turn replay

