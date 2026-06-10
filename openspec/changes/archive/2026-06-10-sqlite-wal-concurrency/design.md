## Context

`db.py` 的 `SQLiteDatabase`（`@dataclass(frozen=True)`）在 `execute` 等处用 `sqlite3.connect(self.path)` 开新连接、不设并发 PRAGMA。默认 rollback journal + `busy_timeout=0` → 并发读写撞锁立即 `database is locked`。#3 物理分库 + §7 只读投影 + 3c 多写者都需要 WAL；当前多 agent 进程单体也已有此隐患。

## Goals / Non-Goals

**Goals:** 经 `db.py` 建立的 SQLite 连接统一启用 WAL + busy_timeout，使并发读写不撞锁失败。

**Non-Goals:** schema/路由/物理分库（#3）；非 SQLite 后端的并发（PG 自有 MVCC，归"可换后端"）；调优 WAL checkpoint 策略（用默认即可）。

## Decisions

**D1 WAL（库级、持久）+ busy_timeout（连接级）。** WAL 设一次写进库文件、后续连接沿用；busy_timeout 每连接设。二者经统一内部入口 `_connect(path)` 设置，`execute` 与游标路径都走它。
- 备选：只设 busy_timeout 不开 WAL。否决——busy_timeout 只解决"写写撞锁等待",WAL 才解决"读写互不阻塞"（§7 读投影 + agent 写并发的关键）。

**D2 落在 `db.py` 连接层，不在 router。** 所有 SQLite 库（含管理库）都该有,db.py 是唯一连接工厂、最通用的一处。
- 备选：只在 router 设。否决——管理库不经 router 也该有 WAL；db.py 一处覆盖全部。

**D3 busy_timeout 取保守值（如 5000ms）。** 共享记忆写低频（经审批门/手工），5s 足够吸收偶发撞锁。

## Risks / Trade-offs

- **`-wal`/`-shm` sidecar 文件**：WAL 正常产物。→ 测试 `tmp_path` 隔离不受影响；备份/拷贝库文件需带上 sidecar（运维文档注明）。
  - **运维操作规范**：备份或拷贝任何由 `db.py` 管理的 SQLite 库时（`fleetent.db`、per-agent 库、KB 库等），必须同时拷贝同目录下的 `<dbfile>-wal` 和 `<dbfile>-shm` 文件（如存在）。仅拷贝 `.db` 主文件会导致 WAL 中未刷回的写入丢失。如需单文件备份，可先用 `sqlite3 <source> "PRAGMA wal_checkpoint(TRUNCATE)"` 强制将 WAL 内容刷回主文件，再拷贝主文件。
- **WAL 要求本地文件系统**（不支持某些网络 FS 的 mmap）。→ on-prem 本地部署满足；将来分布式走 PG 后端、不依赖 SQLite WAL。
- **既有测试受影响?** → WAL/busy_timeout 是连接行为增强、不改数据语义；跑全量确认无回归。

## Migration Plan

- 改 `db.py` 加 `_connect` 统一入口 + PRAGMA；无数据/ schema 变动；无迁移。
- 回滚 = revert（仅连接行为，无持久数据影响；WAL 文件可被后续非 WAL 连接正常读）。
