# im-connector-registry Delta

## MODIFIED Requirements

### Requirement: Connector registry storage
The system SHALL store one row per IM platform connector in an `im_connectors` table with columns: `id`, `owner_id`, `platform` (TEXT), `enabled` (INTEGER default 0), `config` (TEXT JSON, nullable), `status` (TEXT default `stopped`), `last_heartbeat_at` (TEXT, nullable), `last_error` (TEXT, nullable), `created_at`, `updated_at`, with a UNIQUE constraint on `(owner_id, platform)`. （`allowlist_enforced` 列已移除——其唯一用途是 gate 已 descope 的 `im_channel_allowlist`。）

#### Scenario: Table has no allowlist_enforced column
- **WHEN** 检查 `im_connectors` schema at head
- **THEN** 不存在 `allowlist_enforced` 列；其余列与 `(owner_id, platform)` UNIQUE 保留

#### Scenario: Platform uniqueness per owner
- **WHEN** a second row with an existing `(owner_id, platform)` is inserted
- **THEN** the insert is rejected by the UNIQUE constraint
