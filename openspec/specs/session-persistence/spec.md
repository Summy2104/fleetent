## Purpose

Persist per-session conversation history across agent runs, with atomic writes and
per-session isolation, plus the management metadata and controlled write hooks the
admin console needs.
## Requirements
### Requirement: Load session history
The system SHALL load the full conversation history for a session before running the agent. When loading, the system SHALL rehydrate externalized tool results (`[stored:xxx]` references) back to their full inline content, so callers always receive complete messages.

#### Scenario: Existing session
- **WHEN** a message arrives with `session_id` that has an existing `data/sessions/{session_id}.json`
- **THEN** `session_mgr.load(session_id)` returns the full message list from that file

#### Scenario: New session
- **WHEN** a message arrives with a `session_id` that has no existing file
- **THEN** `session_mgr.load(session_id)` returns an empty list

#### Scenario: Externalized tool results rehydrated on load
- **WHEN** a session file contains a tool message whose content is a `[stored:xxx.txt]` reference and the external file exists
- **THEN** `session_mgr.load(session_id)` returns that message with its full content read back inline

### Requirement: Save session history
The system SHALL persist the updated conversation history after each agent run. Before serialization, the system SHALL externalize oversized tool results (>50KB) to per-session external files, persisting references in the session JSON.

#### Scenario: Save after agent completes
- **WHEN** `agent_loop.run()` completes for a session
- **THEN** `session_mgr.save(session_id, updated_messages)` overwrites `data/sessions/{session_id}.json` with the full message list

#### Scenario: Context compression preserved
- **WHEN** `context_mgr` compresses the history during the run
- **THEN** the compressed (shorter) message list is what gets saved, not the original

#### Scenario: Oversized tool result externalized on save
- **WHEN** `save` is called with a tool message whose string content exceeds 50KB
- **THEN** the content is written to `{session_id}.tool_outputs/{tool_call_id}.txt` and the session JSON stores a `[stored:...]` reference instead of the inline content

### Requirement: Session isolation
The system SHALL ensure concurrent sessions do not interfere with each other, both within a single process (asyncio coroutines) and across processes (CLI + server, multiple workers). Same-session writes SHALL be serialized by a two-layer lock: a cross-process file lock (`fcntl.flock` on `{session_id}.lock`) wrapping a per-session in-process `asyncio.Lock`.

#### Scenario: Two sessions run concurrently
- **WHEN** messages for `session_id=A` and `session_id=B` arrive simultaneously
- **THEN** each session loads and saves independently, no data mixing

#### Scenario: Sequential messages in same session
- **WHEN** two messages for the same `session_id` arrive before the first finishes processing
- **THEN** the second message waits (via per-session asyncio.Lock) until the first completes before loading history

#### Scenario: Cross-process writes to same session serialize
- **WHEN** a CLI process and a server process write the same `session_id` concurrently
- **THEN** the file lock serializes them so neither overwrites the other's changes

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

### Requirement: 压缩检查点备份文件管理

系统 SHALL 提供 `write_compaction_checkpoint(session_id, messages)` 和 `delete_compaction_checkpoint(session_id)` 两个函数管理压缩备份文件。`write_compaction_checkpoint` MUST 使用原子写（tmp → rename），`delete_compaction_checkpoint` MUST 静默处理文件不存在的情况。

#### Scenario: 写入压缩检查点
- **WHEN** 调用 `write_compaction_checkpoint(session_id, messages)`
- **THEN** messages 以 JSON 格式原子写入 `data/sessions/{session_id}.pre-compact.json`

#### Scenario: 删除不存在的检查点不报错
- **WHEN** 调用 `delete_compaction_checkpoint(session_id)` 且备份文件不存在
- **THEN** 函数正常返回，不抛出异常

