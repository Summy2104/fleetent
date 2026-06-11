## Context

持久层 #3 把数据从单 `data/fleetent.db` 拆成 5 类物理库、按主体物理分区（`data/<tenant>/<agent_id>/` 目录树），并对所有经 `db.py` 的 SQLite 连接启用 WAL（`database-runtime` 的「SQLite 并发模式」要求）。两处运维工具未跟上：

- `scripts/upgrade.py`：`backup_database()` 只 `shutil.copy2(database_path)` 单个由 `database_url` 解析出的文件。WAL 模式下，未 checkpoint 的写驻留在 `-wal` 中，单文件 copy 会丢这部分写；且完全漏掉所有 per-tenant / per-agent / 共享 / KB / 向量库。
- `observability/diagnostics.py`：`_forbidden_skips` 用 `data_dir.iterdir()` 只遍历顶层，按 `suffix in {.db,.sqlite,...}` 判定 forbidden-skip。子目录（`<tenant>/<agent_id>/`）下的库不被识别为 forbidden，存在被诊断包带出的泄漏风险。

同时管理库的概念名 `management.db` 已在 data-model / target-architecture / specs / `read_projection.py` 注释统一使用，但真实文件仍是 `fleetent.db`（`config.py` / `traces.py` / `user_store.py` / `alembic.ini` / `install*.sh` 多处硬编码）。#3 拆分后该库只剩管理表，是改名收尾时机。

约束：不得绕过 `db.py` 边界私自 `sqlite3.connect`；agent 侧库走嵌入式 Y、不经 Alembic（备份只是文件级复制，不触碰 schema）；改名要兼容旧部署、不破坏存量数据与 WAL 状态。

## Goals / Non-Goals

**Goals:**
- 备份/恢复覆盖数据目录下全部物理库 + WAL，且 WAL 内容不丢（checkpoint 后复制）。
- 诊断 forbidden-skip 递归全树，杜绝子目录库泄漏。
- 管理库 `fleetent.db → management.db` 改名落地，存量部署 upgrade-time 平滑迁移。

**Non-Goals:**
- 多主体跨主体访问校验（Change 2）。
- 在线热备份的事务一致性快照（用 checkpoint + 文件复制的"批次一致"语义，不引入 SQLite Online Backup API 流式增量）。
- 备份保留策略 / 远程备份 / PostgreSQL（仍按既有 deployment 范围排除）。
- agent 侧库 schema 迁移（嵌入式 Y 已落地，不动）。

## Decisions

### D1：备份发现 = 递归扫文件为主 + registry 兜底
对 `data/` 递归 `rglob("*.db")` 枚举待备份库（catch-all，覆盖任意深度、任意命名）；再读管理库 registry（tenants / agents）交叉核对，对"登记但目录缺失"的主体/agent 出告警。**为何不纯 registry 驱动**：registry 驱动会漏掉未登记或停机但留有库文件的情况；递归扫描对文件系统现状最忠实，registry 仅作完整性校验。

### D2：WAL 处理 = checkpoint(TRUNCATE) 后复制主文件
每库复制前经 `db.py` 统一连接入口执行 `PRAGMA wal_checkpoint(TRUNCATE)`，把 `-wal` 落进主文件后再 `copy2` 主文件。**为何不直接 copy 三件套**：copy `.db`+`-wal`+`-shm` 在活动写入下仍可能不一致；checkpoint 先把写固化到主文件，单主文件复制即自洽，恢复更简单。备份过程假定 upgrade 时服务已停或处于静默窗口（与现有 upgrade 语义一致）。

### D3：改名走 upgrade-time 迁移，不做运行时 fallback
`config.py` / `traces.py` / `user_store.py` / `alembic.ini` / `install*.sh` 的默认全部指向 `management.db`；upgrade 时若数据目录有 `fleetent.db` 而无 `management.db`，重命名主文件 + `-wal` + `-shm`，在 backup 之后、`alembic upgrade head` 之前执行，幂等。**为何不运行时自动 fallback 读 fleetent.db**：fallback 会让"旧名仍可用"长期残留、违背单一真相源；一次性 upgrade 迁移干净。显式 `DATABASE_URL` 自定义文件名者不被改名。

### D4：诊断改递归 + 既有判定不变
`_forbidden_skips` 把 `data_dir.iterdir()` 换成 `data_dir.rglob("*.db")`（含按需匹配 `-wal`/`-shm`），其余 forbidden 判定与 manifest 记录逻辑不变。最小改动、行为只扩大覆盖面。

## Risks / Trade-offs

- [备份期间有活动写入导致 checkpoint 后仍有新写未纳入] → upgrade 语义本就建议在停服/静默窗口运行；文档强调；非在线快照场景。
- [改名遗漏某处硬编码 `fleetent.db` 引用，导致指向错文件] → TDD 列出全部引用点逐一改 + 加测试断言默认 `database_url` 与备份/诊断在 `management.db` 上工作；`grep fleetent.db` 收尾核查。
- [递归扫描把无关 `*.db`（如测试残留、第三方）也备份/排除] → 仅作用于配置的 data 目录；可接受（宁多备份/多排除，不漏）。
- [registry 与文件系统不一致（孤儿目录 / 缺失目录）] → 不阻断备份，出告警让 operator 知情。
- [旧部署 WAL 未 checkpoint 即改名] → 改名只是文件 rename（含 sidecar 成组），不解释 WAL 内容；后续首次打开仍能 recover。

## Migration Plan

1. 改默认与硬编码引用（`management.db`）；加 upgrade-time 改名步骤（backup 后、migrate 前、幂等）。
2. 备份/恢复改多库递归 + checkpoint；诊断改递归。
3. 同步 deployment 文档（备份/恢复多库、改名说明）与 `data-model.md` 的"命名对齐"待办勾除。
4. 回滚：本 change 不改 schema；回滚即恢复旧脚本/默认值。已按 `management.db` 迁移的部署回滚需手动改回文件名（文档注明）——故建议改名与备份增强同批上线、一次到位。

## Open Questions

- 无（备份发现策略、WAL 处理、改名机制均已定）。
