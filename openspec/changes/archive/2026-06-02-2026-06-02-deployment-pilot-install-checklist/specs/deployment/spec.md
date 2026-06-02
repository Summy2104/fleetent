## ADDED Requirements

### Requirement: Pilot install checklist
部署文档 SHALL 提供 Pilot MVP 安装清单，按 operator 执行顺序覆盖安装、升级、备份、启动、健康检查、排障、回滚和验收。

#### Scenario: Checklist document exists
- **WHEN** operator 查看 deployment 文档
- **THEN** 文档引用 `docs/deployment/pilot-install-checklist.md`
- **AND** checklist 使用中文说明 Pilot 安装与验收步骤

#### Scenario: Checklist covers install and upgrade
- **WHEN** operator 阅读 checklist
- **THEN** checklist 包含前置条件、配置、`scripts/upgrade.py --dry-run`、SQLite backup、`alembic upgrade head`、服务启动和 `/health` 检查

#### Scenario: Checklist covers Pilot operations
- **WHEN** operator 阅读 checklist
- **THEN** checklist 包含 KB connector check / sync / status、observability traces / usage / performance 查询、diagnostics export / retention dry-run

#### Scenario: Checklist covers rollback and reporting
- **WHEN** operator 阅读 checklist
- **THEN** checklist 包含从 SQLite backup 手动恢复、停止服务、重启服务、回滚后 health check 和问题上报包

#### Scenario: Checklist excludes secrets
- **WHEN** operator 阅读 checklist 或准备问题上报包
- **THEN** checklist 明确禁止把真实 secret、token、credential payload 写入 settings、日志、trace、diagnostics package、issue 或测试 fixture
