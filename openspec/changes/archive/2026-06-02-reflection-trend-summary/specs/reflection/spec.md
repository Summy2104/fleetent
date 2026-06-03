## ADDED Requirements

### Requirement: Reflection trend summary design
reflection SHALL provide an on-demand trend summary over existing reflection reports and proposal lifecycle records.

#### Scenario: Trend summary API is importable
- **WHEN** callers import `ReflectionTrendQuery`, `ReflectionTrendBucket`, `ReflectionTrendSummary`, and `get_reflection_trend_summary`
- **THEN** the imports succeed

#### Scenario: Trend summary reads reflection-owned sources
- **WHEN** a trend summary is generated
- **THEN** it reads only reflection-owned reports and proposal lifecycle tables
- **AND** it does not read raw transcripts or module-internal memory / KB / skill stores

#### Scenario: Findings are bucketed
- **WHEN** reports exist across multiple UTC buckets
- **THEN** the summary returns per-bucket finding counts by finding type

#### Scenario: Proposal lifecycle is aggregated
- **WHEN** memory maintenance and skill proposals exist
- **THEN** the summary returns per-bucket counts by proposal status, risk, and type/action

#### Scenario: Trend summary is non-mutating
- **WHEN** trend summary runs
- **THEN** it does not create proposals
- **AND** it does not write Memory, Knowledge Base, or Skill content
