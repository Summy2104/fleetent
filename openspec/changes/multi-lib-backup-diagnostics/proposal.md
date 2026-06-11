## Why

持久层 #3 把数据从单库拆成 5 类物理库、按主体物理分区（`<tenant>/<agent_id>/` 目录），并对所有 SQLite 连接启用 WAL。但两处运维工具仍停在单库世界：`scripts/upgrade.py` 的备份只 `shutil.copy2` 单个 `database_url` 文件，`observability/diagnostics.py` 的 forbidden-skip 只扫 `data_dir` 顶层——前者会**漏备份所有 per-tenant / per-agent / 共享 / KB / 向量库 + WAL sidecar（数据丢失）**，后者会**让 per-tenant 子目录库被诊断包带出（泄漏）**。两者都是 Pilot Go 判据相关。同时，管理库的概念名 `management.db` 已在 data-model / target-architecture / specs / `read_projection.py` 注释中统一使用，但真实文件仍是 `fleetent.db`，#3 拆分后该库只剩管理表，是改名收尾的时机。

## What Changes

- **备份/恢复多库化**（`scripts/upgrade.py`）：从「只 copy 单个 `database_url` 文件」改为**递归遍历 `data/` 下所有 `*.db`（任意深度）+ 各自 `-wal`/`-shm` sidecar**；每库备份前 `PRAGMA wal_checkpoint(TRUNCATE)` 再 copy（WAL 下直接 copy 主文件会丢未 checkpoint 的写）；以 management.db registry 交叉核对发现的主体/agent（递归扫为主、registry 兜底校验，发现停机 agent 的库也不漏）。恢复对称。`--backup-only` / `--dry-run` 行为随之覆盖全部库。
- **诊断排除递归化**（`observability/diagnostics.py`）：`_forbidden_skips` 从顶层 `data_dir.iterdir()` 改为递归 `rglob("*.db")`（含 `-wal`/`-shm`），所有物理库一律纳入 forbidden-skip，manifest 记录跳过原因。
- **管理库改名 `fleetent.db → management.db`**（**BREAKING**：默认 DB 文件名变更，含 upgrade-time 迁移）：`database_url` 默认值、`traces.py` 默认、`user_store.py` DB_PATH、`alembic.ini` `sqlalchemy.url`、`scripts/install*.sh` 的 sed 替换全部指向 `management.db`；upgrade 时若 `management.db` 不存在而 `fleetent.db` 存在，则重命名主文件 + `-wal`/`-shm`（兼容旧部署，不破坏存量数据）。

## Capabilities

### New Capabilities
<!-- 无新增能力；均为既有能力的需求修改 -->

### Modified Capabilities
- `database-runtime`: 默认管理库文件名由 `data/fleetent.db` 改为 `data/management.db`；新增 upgrade-time「`fleetent.db` → `management.db` 重命名（含 WAL sidecar）」兼容迁移要求。
- `deployment`: pre-migration 备份、restore、backup-only 由「单 `fleetent.db` 文件」改为「递归覆盖 `data/` 下全部物理库 + WAL sidecar，且每库 checkpoint 后再备份」；备份/恢复文档同步反映多库。
- `diagnostics-redaction-export-hardening`: forbidden-artifact 跳过由「顶层目录扫描」改为「递归全树 `*.db` / WAL」，per-tenant 子目录库不再被诊断包带出。

## Impact

- **代码**：`scripts/upgrade.py`（备份/恢复/改名迁移）、`observability/diagnostics.py`（`_forbidden_skips` 递归）、`config.py`（`database_url` 默认）、`observability/traces.py`（默认 URL）、`user_store.py`（`DB_PATH`）、`alembic.ini`、`scripts/install.sh` / `scripts/install-platform.sh`。
- **配置**：`database_url` 默认值（`management.db`）；`DATABASE_URL` 显式设置者不受影响。
- **依赖**：备份发现读 management.db registry / `tenant_router` 的 `<tenant>/<agent_id>/` 文件布局（只读 enumerate，不绕过 `db.py` 边界）。
- **兼容**：旧部署（`fleetent.db` 存量）经 upgrade-time 重命名平滑迁移；非 SQLite / 远程 / `:memory:` 仍 fail fast。
- **不在本切片**：多主体跨主体访问校验（属 Change 2 `wire-tenant-check-and-principal`）；agent 侧库迁移引擎（嵌入式 Y，已落地，不动）。
