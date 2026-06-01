## 0. 前置确认

- [x] 0.1 确认 `database-default-path-rename` 已完成或本 change 基于 `data/fleetent.db` 默认路径实现
- [x] 0.2 确认本 change 只支持本地 SQLite database_url
- [x] 0.3 确认不做自动 rollback、不做 PostgreSQL、不做 Admin API / UI

## 1. Backup path and database URL validation

- [x] 1.1 Write failing tests: upgrade script 按 `--database-url`、`DATABASE_URL`、`Settings().database_url` 优先级解析本地 SQLite DB path
- [x] 1.2 Write failing tests: 非 SQLite 或非本地 SQLite URL fail fast，且不创建备份
- [x] 1.3 Write failing tests: 非 dry-run 模式下缺失 DB 文件 fail fast，且错误信息说明 database file 不存在
- [x] 1.4 Implement: database URL validation and path resolution helpers
- [x] 1.5 Verify green: 运行 `uv run pytest tests/unit/test_upgrade_script.py -x -q`

## 2. SQLite backup

- [x] 2.1 Write failing tests: 默认备份写入 `data/backups/YYYYMMDD-HHMMSS/fleetent.db`
- [x] 2.2 Write failing tests: `--backup-dir` 可覆盖默认 backup root
- [x] 2.3 Write failing tests: backup 会创建缺失的 backup directory
- [x] 2.4 Write failing tests: 备份文件内容与源 DB 文件一致
- [x] 2.5 Implement: timestamped SQLite file backup
- [x] 2.6 Verify green: 运行 `uv run pytest tests/unit/test_upgrade_script.py -x -q`

## 3. Dry run and backup-only modes

- [x] 3.1 Write failing tests: `--dry-run` 输出将执行的 backup 和 migration 操作，但不要求 DB 文件存在、不写文件、不调用 Alembic
- [x] 3.2 Write failing tests: `--backup-only` 创建备份但不调用 Alembic
- [x] 3.3 Implement: CLI flags and execution branching
- [x] 3.4 Verify green: 运行 `uv run pytest tests/unit/test_upgrade_script.py -x -q`

## 4. Alembic upgrade execution

- [x] 4.1 Write failing tests: 默认流程在 backup 成功后调用 `alembic upgrade head`
- [x] 4.2 Write failing tests: backup 失败时不调用 Alembic，并返回非 0
- [x] 4.3 Write failing tests: Alembic 失败时返回非 0，并保留已创建 backup
- [x] 4.4 Implement: subprocess Alembic invocation and exit code handling
- [x] 4.5 Verify green: 运行 `uv run pytest tests/unit/test_upgrade_script.py -x -q`

## 5. Integration smoke

- [x] 5.1 Write failing tests: 在 tmp_path 中创建 SQLite DB，运行 upgrade dry-run 不触碰真实 `data/`
- [x] 5.2 Write failing tests: 在 tmp_path 中创建 SQLite DB，运行 backup-only 生成可恢复备份
- [x] 5.3 Implement: integration fixes discovered by smoke tests
- [x] 5.4 Verify green: 运行 `uv run pytest tests/integration/test_upgrade_script.py -x -q`

## 6. Docs and final verification

- [x] 6.1 更新 `docs/capabilities/deployment.md`
- [x] 6.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 6.3 文档写明手动恢复步骤：停服务、用 backup 替换 DB 文件、重启服务
- [x] 6.4 文档写明 migration 失败不会自动 rollback
- [x] 6.5 运行 `uv run ruff format src tests`
- [x] 6.6 运行 `uv run ruff check src tests`
- [x] 6.7 运行 `uv run mypy src`
- [x] 6.8 运行 `uv run pytest -x -q`
- [x] 6.9 运行 `openspec validate deployment-upgrade-and-backup --strict`
- [x] 6.10 运行 `git diff --check`
