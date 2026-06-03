# manual-maintenance-entrypoints Specification

## Purpose
TBD - created by archiving change manual-maintenance-entrypoints. Update Purpose after archive.
## Requirements
### Requirement: Dry-run first maintenance commands

Manual maintenance entrypoints SHALL support dry-run before mutation. Destructive operations SHALL require an
explicit confirmation flag such as `--yes`. This capability SHALL provide manual operator-triggered maintenance
only and SHALL NOT add scheduler or worker automation.

#### Scenario: Apply without confirmation
- **WHEN** an operator runs a destructive maintenance command without `--yes`
- **THEN** the command exits before mutation
- **AND** prints the dry-run command or confirmation requirement

### Requirement: Maintenance summaries

Manual maintenance entrypoints SHALL emit human-readable and JSON summaries with affected counts, dry-run/apply
mode, skipped reasons and audit/trace reference when mutation occurs.

#### Scenario: Memory compaction apply
- **WHEN** memory compaction is applied
- **THEN** the summary includes affected counts and an audit or observability reference

#### Scenario: Reflection proposal approval
- **WHEN** a reflection proposal is approved or rejected through a manual maintenance entrypoint
- **THEN** the summary includes the proposal id, outcome and audit or observability reference

### Requirement: Shared Memory edits use proposal lifecycle

Manual maintenance entrypoints SHALL NOT provide direct Shared Memory admin edits in this change. Shared Memory
changes SHALL use proposal/apply lifecycle entrypoints.

#### Scenario: Direct shared memory edit is requested
- **WHEN** an operator attempts to directly edit Shared Memory through this maintenance surface
- **THEN** the command is unavailable or rejected
- **AND** the operator is directed to the proposal/apply lifecycle

### Requirement: Public API boundaries

Manual maintenance entrypoints SHALL call owner module public APIs rather than importing internal implementation
details.

#### Scenario: Vector rebuild
- **WHEN** vector rebuild is run from admin CLI
- **THEN** it uses vector store public reindex API
- **AND** reports namespace/source counts before mutation

