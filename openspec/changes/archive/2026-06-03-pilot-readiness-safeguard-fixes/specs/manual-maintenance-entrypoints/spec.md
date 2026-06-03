## MODIFIED Requirements

### Requirement: Maintenance summaries

Manual maintenance entrypoints SHALL emit human-readable and JSON summaries with affected counts, dry-run/apply
mode, skipped reasons and audit/trace reference when mutation occurs. For Pilot, mutation references SHALL be
real observability trace evidence recorded through the observability public API, not synthetic placeholder strings.

#### Scenario: Memory compaction apply
- **WHEN** memory compaction is applied
- **THEN** the summary includes affected counts and an audit or observability reference
- **AND** the referenced observability evidence exists

#### Scenario: Reflection proposal approval
- **WHEN** a reflection proposal is approved or rejected through a manual maintenance entrypoint
- **THEN** the summary includes the proposal id, outcome and audit or observability reference

#### Scenario: Dry-run does not create mutation evidence
- **WHEN** a maintenance dry-run command is executed
- **THEN** it reports candidate affected counts
- **AND** it does not create mutation trace evidence
