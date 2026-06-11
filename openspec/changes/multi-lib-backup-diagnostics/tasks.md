## 1. 管理库改名 fleetent.db → management.db（默认与硬编码引用）

- [x] 1.1 写测试（unit）：未显式配置时默认 `database_url` 指向 `data/management.db`；旧 `fleetent.db` 不再是默认 —— 见红
- [x] 1.2 改 `config.py` `database_url` 默认 factory → `management.db`；`observability/traces.py` 默认 URL → `management.db`；`user_store.py` `DB_PATH` → `management.db` —— 见绿
- [x] 1.3 改 `alembic.ini` 默认 `sqlalchemy.url` 与 `scripts/install.sh` / `scripts/install-platform.sh` 中 sed 替换的 `fleetent.db` → `management.db`
- [x] 1.4 收尾 `grep -rn "fleetent\.db" src scripts alembic.ini`：确认仅剩有意的兼容迁移引用（`runtime/agent_app.py` standalone-agent DB + 概念性 docstring，非管理库），无残留管理库默认硬编码

## 2. Upgrade-time 改名迁移（兼容旧部署）

- [x] 2.1 写测试（integration）：数据目录有 `fleetent.db`(+`-wal`/`-shm`)无 `management.db` → upgrade 后三件套重命名为 `management.db*`，在 backup 之后、migrate 之前 —— 见红
- [x] 2.2 写测试（integration）：已存在 `management.db` → 迁移幂等不重命名；显式 `DATABASE_URL` 自定义文件名 → 不被改名 —— 见红
- [x] 2.3 在 `scripts/upgrade.py` 实现改名步骤（backup 成功后、`alembic upgrade head` 前，幂等，含 WAL sidecar） —— 见绿

## 3. 备份/恢复覆盖全部物理库 + WAL checkpoint

- [x] 3.1 写测试（integration）：构造含 `<tenant>/kb.db`、`<tenant>/shared_memory.db`、`<tenant>/<agent_id>/agent_state.db` + 各 `*_vectors.db` 的数据目录，默认 upgrade 后 `data/backups/TS/` 镜像结构备份**每一个**库 —— 见红
- [x] 3.2 写测试（integration）：某库有未 checkpoint 的 WAL 写 → 备份前 `wal_checkpoint(TRUNCATE)`，备份副本含该写（不丢） —— 见红
- [x] 3.3 写测试（integration）：停机 agent 的 `agent_state.db` 仍被递归发现并备份；registry 登记但目录缺失 → 告警不静默；`--backup-only` 同样覆盖全部库 —— 见红
- [x] 3.4 重写 `scripts/upgrade.py` 的 `backup_database`：递归 `rglob("*.db")` 枚举 + 每库经 `db.py` 入口 `wal_checkpoint(TRUNCATE)` 后复制 + 镜像目录结构；读 management.db registry 交叉核对兜底告警 —— 见绿
- [x] 3.5 写测试（integration）+ 实现：恢复对称（用备份批次整体替换数据目录全部库，含子目录） —— 见红→见绿

## 4. 诊断 forbidden-skip 递归全树

- [x] 4.1 写测试（integration）：数据目录子目录下的 `agent_state.db` / `kb.db`（+WAL）在 diagnostics export 中被排除，manifest 逐一记录每个被跳过的库（含子目录路径） —— 见红
- [x] 4.2 把 `observability/diagnostics.py` 的 `_forbidden_skips` 由 `data_dir.iterdir()` 改为递归 `rglob("*.db")`（含 `-wal`/`-shm`），既有 forbidden 判定与 manifest 逻辑不变 —— 见绿

## 5. 文档同步与收尾

- [x] 5.1 更新 `docs/capabilities/deployment.md`：备份/恢复多库 + WAL checkpoint、`management.db` 默认与改名说明、backup 路径镜像结构
- [x] 5.2 勾除 `docs/architecture/data-model.md` 文末「命名对齐」待办（改名已落地），并把 §1 layout 注释从「概念名」改为现状
- [ ] 5.3 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
