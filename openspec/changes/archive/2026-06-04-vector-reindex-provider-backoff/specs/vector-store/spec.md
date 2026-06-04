## ADDED Requirements

### Requirement: Reindex handles transient provider throttling
Vector reindex SHALL avoid turning transient embedding provider throttling into a failed full rebuild when bounded retry can recover.

#### Scenario: Transient upsert failure is retried
- **WHEN** reindexing a vector namespace
- **AND** a single item upsert fails once with a transient provider error
- **THEN** the executor retries that item before moving on
- **AND** the item is counted as reindexed if the retry succeeds

#### Scenario: Per-item pacing is applied
- **WHEN** reindexing multiple items
- **THEN** the executor applies a small pacing delay between item attempts
- **AND** the delay is injectable in tests so default tests do not sleep

#### Scenario: Persistent failures remain isolated
- **WHEN** an item still fails after the retry budget is exhausted
- **THEN** the executor counts only that item as failed
- **AND** continues processing later items
