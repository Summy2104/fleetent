## MODIFIED Requirements

### Requirement: Session metadata

The system SHALL store session-level metadata alongside the message history: `origin` (`web` / `im` / `playground`), `status` (`active` / `idle` / `ended`), `takeover` (active takeover actor + start time, empty when in automatic mode), and `pinned` (retention flag + note). Existing load/save/lock/isolation semantics are unchanged. Existing sessions SHALL backfill `origin` from their source and default `status=active`, `takeover`/`pinned` empty.

#### Scenario: New playground session marks origin

- **WHEN** a session is started from the admin playground
- **THEN** its metadata records `origin=playground`

#### Scenario: Existing session backfills origin

- **WHEN** an existing web or IM session is read after the migration
- **THEN** its `origin` is `web` or `im` respectively and `status` defaults to `active`

### Requirement: Controlled write hooks

The system SHALL expose controlled write hooks for the management plane, reusing the existing per-session `asyncio.Lock` and atomic write: `force_end(session_id)` marks the session `ended` so it no longer accepts new turns; `clear(session_id)` empties the session context (equivalent to im-gateway `/new`); `inject_message(session_id, role, content)` appends a human / assistant message to the transcript. These hooks SHALL NOT change load/save semantics or break session isolation.

#### Scenario: Force end stops new turns

- **WHEN** `session_mgr.force_end(session_id)` is called
- **THEN** the session metadata `status` becomes `ended` and subsequent turns are not accepted

#### Scenario: Clear empties context

- **WHEN** `session_mgr.clear(session_id)` is called
- **THEN** the session's message list is emptied (equivalent to `/new`) and the next run starts from empty context

#### Scenario: Inject message under lock

- **WHEN** `session_mgr.inject_message(session_id, role, content)` is called
- **THEN** the message is appended atomically under the per-session lock and persisted, without mixing with concurrent sessions

#### Scenario: Hooks preserve isolation

- **WHEN** write hooks are called on `session_id=A` while `session_id=B` runs concurrently
- **THEN** each session loads and saves independently with no data mixing
