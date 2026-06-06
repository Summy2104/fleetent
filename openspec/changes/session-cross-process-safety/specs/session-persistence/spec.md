## MODIFIED Requirements

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
