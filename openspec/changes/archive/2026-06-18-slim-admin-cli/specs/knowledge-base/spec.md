## REMOVED Requirements

### Requirement: Admin CLI connector operations
**Reason**: 迁移到现有 HTTP API `/admin/kb/connectors/*`（list/check/status/sync 均已存在）。CLI 入口冗余。
**Migration**:
- `kb connectors list` → `GET /admin/kb/connectors`
- `kb connectors check <id>` → `POST /admin/kb/connectors/{id}/check`
- `kb connectors status <id>` → `GET /admin/kb/connectors/{id}/status`
- `kb connectors sync <id> [--dry-run]` → `POST /admin/kb/connectors/{id}/sync`（body `dry_run`）

> 注：CLI 的 execute-sync 三重防误触闸门（`--yes` + `--pilot-fixture` + `FLEETENT_*_EXECUTE_SYNC=1` 环境变量）在 HTTP 侧无对应；如需生产防误触保护应在 HTTP 端点层另行评估。`kb extract-entities` 命令保留（不在本次删除范围）。

#### Scenario: List connectors from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors list`
- **THEN** CLI 输出配置的 connector 摘要

#### Scenario: Check connector from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors check <connector_id>`
- **THEN** CLI 输出该 connector 的检查状态

#### Scenario: Show connector status from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors status <connector_id>`
- **THEN** CLI 输出该 connector 最近一次状态或 `never_run`

#### Scenario: Dry-run sync from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors sync <connector_id> --dry-run`
- **THEN** CLI 执行 dry-run 并输出 plan summary

#### Scenario: Run sync from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors sync <connector_id>`
- **THEN** CLI 执行真实 sync 并输出 sync summary

#### Scenario: CLI output is sanitized
- **WHEN** CLI 输出 connector check、sync 或 status 结果
- **THEN** 输出不包含 token、secret、credential payload 或完整文档正文
