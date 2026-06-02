## ADDED Requirements

### Requirement: Memory quality trend summary design
memory-layer SHALL provide a read-only trend summary for User Memory quality, Shared Memory state, and memory maintenance proposal outcomes.

#### Scenario: Memory quality trend API is importable
- **WHEN** callers import `MemoryQualityTrendQuery`, `MemoryQualityTrendBucket`, `MemoryQualityTrendSummary`, and `get_memory_quality_trend_summary`
- **THEN** the imports succeed

#### Scenario: User Memory counts are bucketed
- **WHEN** User Memory records exist across multiple time buckets
- **THEN** the summary reports counts by memory type and bucket

#### Scenario: Shared Memory remains separate
- **WHEN** Shared Memory records exist
- **THEN** the summary reports Shared Memory counts separately from User Memory counts

#### Scenario: Maintenance proposal outcomes are included
- **WHEN** memory maintenance proposals exist
- **THEN** the summary reports counts by action, risk, and status

#### Scenario: Summary is non-mutating
- **WHEN** the quality trend summary runs
- **THEN** it does not create, update, archive, or delete User Memory or Shared Memory
