## Why

`db.py` 的 `SQLiteDatabase` 每次操作 `sqlite3.connect(self.path)` 开新连接，**不设任何并发 PRAGMA**（无 `journal_mode=WAL`、无 `busy_timeout`）。默认 = rollback journal + `busy_timeout=0`：一旦并发读写同一库，撞锁**立即** `database is locked` 报错。

这是物理分库（#3）+ **§7 platform 只读投影**的**地基前提**：platform 读 agent 库时 agent 在写（KB ingest 写 / per-agent 写 / 共享记忆多 agent 写）——只有 **WAL** 能"读不挡写、写不挡读"；多写者撞锁需 **busy_timeout** 短暂等待重试而非立即失败。也顺手修掉**当前多 agent 进程单体下本就存在的隐患**。这是个独立、低风险的横切地基修复，早做让 §7 / 3c / 3a-KB 的并发前提就位。

## What Changes

- `db.py` 的 `SQLiteDatabase` 在每次建立 SQLite 连接时设并发 PRAGMA：`PRAGMA journal_mode=WAL`（库级、持久、幂等）+ `PRAGMA busy_timeout=<ms>`（连接级，合理超时如 5000ms）。
- 经一个统一的内部连接入口（如 `_connect(path)`）设置，覆盖 `execute` 与游标/迭代等所有打开连接的路径，**所有经 `db.py` 的 SQLite 库统一受益**（管理库 / KB / per-agent / 共享记忆）。

不在本切片：路由 / 物理分库（#3）；任何 schema 改动；非 SQLite 后端（WAL 是 SQLite 专属，PG 后端有自己的 MVCC，由"可换后端"另行处理）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `database-runtime`: 新增"SQLite 并发模式"要求——经 `db.py` 建立的 SQLite 连接 SHALL 启用 WAL + 设置 `busy_timeout`，使并发读写（含 platform 只读投影读 + agent 写）不因默认 journal/零超时而撞锁失败。

## Impact

- **代码**：仅 `db.py`（连接构造处加 PRAGMA + 统一连接入口）。
- **运行时**：每个 SQLite 库文件旁会出现 `-wal` / `-shm` sidecar 文件（WAL 正常产物）；测试 `tmp_path` 隔离不受影响。
- **约束遵守**：不扩散裸 `sqlite3.connect`（恰恰收敛到统一入口）；不碰业务层。
- **风险**：低。WAL 普遍更优；唯一注意 WAL 要求库文件在支持 mmap 的本地文件系统（本地部署满足）。
- **依赖文档**：data-model.md §5.2（嵌入式迁移/连接）、target-architecture-proposal.md §7（只读投影的并发前提）。
