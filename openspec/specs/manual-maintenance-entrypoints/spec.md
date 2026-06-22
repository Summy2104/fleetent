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

### Requirement: Shared Memory edits use proposal lifecycle

任何平台面——维护命令面(`maintenance`)、专用 admin CLI(`memory shared *`)、以及平台 HTTP API(`/admin/memory/*`)——SHALL NOT 提供共享记忆的直接编辑(create/update/archive)。共享记忆改动 SHALL 走 agent 侧 proposal/apply 生命周期(reflection 提议 → 审批门 → apply)。平台可读共享记忆作投影,但不提供绕过治理的直写入口。

#### Scenario: 维护面不提供共享记忆直接编辑

- **WHEN** operator 试图经 `maintenance` 维护面直接编辑共享记忆
- **THEN** 该操作不可用或被拒绝
- **AND** operator 被引导到 proposal/apply 生命周期

#### Scenario: 平台无专用共享记忆直写入口

- **WHEN** 查看 `fleetent admin` 子命令与平台 HTTP API
- **THEN** 不存在 `memory shared create/update/archive` CLI,也不存在 `/admin/memory/shared` 直写端点

#### Scenario: 共享记忆改动经 agent 侧生命周期

- **WHEN** 系统需要新增或修改一条共享记忆
- **THEN** 经 reflection 提议 → 审批 → apply 落地(`apply_shared_memory_proposal`),而非平台直写

### Requirement: Public API boundaries

Manual maintenance entrypoints SHALL call owner module public APIs rather than importing internal implementation
details.

#### Scenario: Vector rebuild
- **WHEN** vector rebuild is run from admin CLI
- **THEN** it uses vector store public reindex API
- **AND** reports namespace/source counts before mutation

