## ADDED Requirements

### Requirement: Load session history
The system SHALL load the full conversation history for a session before running the agent.

#### Scenario: Existing session
- **WHEN** a message arrives with `session_id` that has an existing `data/sessions/{session_id}.json`
- **THEN** `session_mgr.load(session_id)` returns the full message list from that file

#### Scenario: New session
- **WHEN** a message arrives with a `session_id` that has no existing file
- **THEN** `session_mgr.load(session_id)` returns an empty list

### Requirement: Save session history
The system SHALL persist the updated conversation history after each agent run.

#### Scenario: Save after agent completes
- **WHEN** `agent_loop.run()` completes for a session
- **THEN** `session_mgr.save(session_id, updated_messages)` overwrites `data/sessions/{session_id}.json` with the full message list

#### Scenario: Context compression preserved
- **WHEN** `context_mgr` compresses the history during the run
- **THEN** the compressed (shorter) message list is what gets saved, not the original

### Requirement: Session isolation
The system SHALL ensure concurrent sessions do not interfere with each other.

#### Scenario: Two sessions run concurrently
- **WHEN** messages for `session_id=A` and `session_id=B` arrive simultaneously
- **THEN** each session loads and saves independently, no data mixing

#### Scenario: Sequential messages in same session
- **WHEN** two messages for the same `session_id` arrive before the first finishes processing
- **THEN** the second message waits (via per-session asyncio.Lock) until the first completes before loading history
