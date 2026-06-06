## MODIFIED Requirements

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
- **THEN** `session_mgr.save(session_id, updated_messages)` overwrites `data/sessions/{session_id}.json` with the message list

#### Scenario: Context compression preserved
- **WHEN** `context_mgr` compresses the history during the run
- **THEN** the compressed (shorter) message list is what gets saved, not the original

#### Scenario: Oversized tool result externalized on save
- **WHEN** `save` is called with a tool message whose string content exceeds 50KB
- **THEN** the content is written to `{session_id}.tool_outputs/{tool_call_id}.txt` and the session JSON stores a `[stored:...]` reference instead of the inline content
