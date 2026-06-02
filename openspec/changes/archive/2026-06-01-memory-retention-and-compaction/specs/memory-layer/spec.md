## ADDED Requirements

### Requirement: Memory retention maintenance public API
memory-layer SHALL provide a per-user public API for dry-run and apply memory retention maintenance.

#### Scenario: Maintenance API is importable
- **WHEN** 调用方从 `fleetent.memory_layer` 导入 maintenance policy、summary、candidate dataclasses 和 `run_memory_maintenance`
- **THEN** 导入成功

#### Scenario: Invalid maintenance request fails fast
- **WHEN** caller passes empty user_id or negative per-type limits
- **THEN** maintenance API raises a validation error

#### Scenario: Maintenance is user scoped
- **WHEN** caller runs maintenance for user A
- **THEN** maintenance does not delete user B memory rows
- **AND** vector deletion namespace is `mem:{user_a}`

### Requirement: Memory retention dry-run
memory-layer SHALL support dry-run retention maintenance that reports eligible rows without mutation.

#### Scenario: Dry-run reports expired context rows
- **WHEN** user has context memory with `expires_at` before now
- **AND** maintenance runs with dry_run enabled
- **THEN** summary reports the expired memory id
- **AND** SQLite row remains
- **AND** vector_store.delete is not called

#### Scenario: Dry-run reports over-limit rows
- **WHEN** user has more memories of a type than policy allows
- **AND** maintenance runs with dry_run enabled
- **THEN** summary reports older over-limit memory ids
- **AND** SQLite rows remain
- **AND** vector_store.delete is not called

### Requirement: Memory retention apply
memory-layer SHALL delete eligible per-user memory rows and matching vectors when retention maintenance is applied.

#### Scenario: Apply deletes expired context rows
- **WHEN** user has context memory with `expires_at` before now
- **AND** maintenance runs with dry_run disabled
- **THEN** expired context row is deleted from `memory_items`
- **AND** vector_store.delete is called for that memory id

#### Scenario: Apply deletes older over-limit rows
- **WHEN** user has more memories of a type than policy allows
- **AND** maintenance runs with dry_run disabled
- **THEN** newest memories within the limit are retained
- **AND** older over-limit rows are deleted

### Requirement: Memory duplicate compaction
memory-layer SHALL provide deterministic duplicate compaction candidates within the same user and memory type.

#### Scenario: Duplicate candidate is reported
- **WHEN** user has multiple memories of the same type with identical normalized content
- **THEN** maintenance summary includes a compaction candidate with one canonical id and duplicate ids

#### Scenario: Newest duplicate is canonical
- **WHEN** duplicate memories have different updated_at values
- **THEN** canonical id is the newest row, using id as stable tie-breaker

#### Scenario: Apply duplicate compaction removes duplicates
- **WHEN** maintenance runs with dry_run disabled and duplicate compaction enabled
- **THEN** duplicate ids are deleted
- **AND** canonical id remains
