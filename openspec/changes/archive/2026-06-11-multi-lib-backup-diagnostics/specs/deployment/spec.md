## MODIFIED Requirements

### Requirement: Pre-migration SQLite backup
upgrade script SHALL 在运行 Alembic migration 前创建 SQLite 备份，且备份 SHALL 覆盖数据目录下**全部物理库**（持久层 #3：管理库 + per-tenant 的 KB / 共享记忆库 + per-agent 运行库 + 各向量库），而非仅管理库单文件。

#### Scenario: Backup covers all physical databases before migration
- **WHEN** operator 运行默认 upgrade
- **THEN** script 在 `data/backups/YYYYMMDD-HHMMSS/` 下按原数据目录相对结构备份**每一个** `*.db`（含 `<tenant>/` 与 `<tenant>/<agent_id>/` 子目录下的库）
- **AND** 每库在复制前执行 `PRAGMA wal_checkpoint(TRUNCATE)`，确保 WAL 中未落盘的写被纳入备份
- **AND** 所有库备份成功后才运行 `alembic upgrade head`

#### Scenario: WAL sidecar 一并备份
- **WHEN** 某库存在 `-wal` / `-shm` sidecar
- **THEN** 备份在 checkpoint 后复制主文件；如保留 sidecar 则与主文件成组复制，恢复后不破坏一致性

#### Scenario: Backup directory is created
- **WHEN** backup directory 不存在
- **THEN** script 创建该目录（含镜像子目录结构）

#### Scenario: Missing management database fails fast
- **WHEN** `database_url` 指向的管理库文件不存在
- **THEN** script fail fast
- **AND** 错误信息说明 management database file 不存在
- **AND** 不运行 Alembic migration

### Requirement: Backup-only mode
upgrade script SHALL 支持 backup-only，用于只创建 SQLite 备份而不运行 migration；该备份 SHALL 同样覆盖全部物理库。

#### Scenario: Backup-only skips migration
- **WHEN** operator 运行 `scripts/upgrade.py --backup-only`
- **THEN** script 备份数据目录下全部物理库（每库 checkpoint 后复制）
- **AND** 不运行 Alembic migration

### Requirement: Manual restore documentation
部署文档 SHALL 说明 upgrade 失败后的手动恢复步骤，且步骤 SHALL 覆盖多物理库恢复。

#### Scenario: Restore steps are documented
- **WHEN** operator 查看 deployment 文档
- **THEN** 文档说明恢复步骤：停止服务、用备份目录整体替换数据目录下对应的全部库文件（含 `<tenant>/<agent_id>/` 子目录），重启服务
- **AND** 文档说明 migration 失败不会自动 rollback
- **AND** 文档说明恢复需保证同一备份批次的各库一致，不混用不同时间点的备份

## ADDED Requirements

### Requirement: Multi-database backup discovery
备份 SHALL 通过递归枚举数据目录下所有 `*.db`（任意深度）发现待备份库；并 SHALL 以管理库 registry（tenants / agents）交叉核对，以覆盖**进程未运行**的主体 / agent 的库（递归扫描为主、registry 兜底校验）。备份枚举与复制 SHALL NOT 绕过统一 `db.py` 边界私自 `sqlite3.connect()`（checkpoint 经统一连接入口完成）。

#### Scenario: 停机 agent 的库也被备份
- **WHEN** 某 agent 进程未运行，但其 `<tenant>/<agent_id>/agent_state.db` 存在
- **THEN** 备份递归枚举到该文件并纳入备份集
- **AND** registry 中登记但目录缺失的主体 / agent 在备份输出中以告警形式提示，而非静默跳过

#### Scenario: 备份不遗漏向量库
- **WHEN** 数据目录含 `agent_vectors.db` / `kb_vectors.db` / `shared_memory_vectors.db`
- **THEN** 这些向量库与关系库一同被发现并备份
