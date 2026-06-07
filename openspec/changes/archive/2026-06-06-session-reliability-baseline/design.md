## Context

Session 系统由两层组成：消息文件（JSON，`data/sessions/`）和元数据索引（SQLite `sessions` 表）。当前实现存在三个独立缺陷：

1. `session/manager.py` 使用 structlog，与本项目自定义结构化日志（`structured_logging.py`）脱节，session 操作日志不落盘、不脱敏
2. `cleanup_expired()` 和 `enforce_capacity()` 只删除文件，不同步删除 SQLite 中的对应行，导致 `count()`/`list_by_user()` 持续返回幽灵记录
3. `list_by_user()` 无 LIMIT 子句，全量查询随 session 积累性能线性下降

三处修复均在 `session/` 包内，互相独立，无外部依赖变更。

## Goals / Non-Goals

**Goals:**
- session 模块所有日志统一走 `get_logger("session.manager")`，落盘、脱敏
- TTL 清理与容量淘汰删除文件后同步删除 SQLite 索引行，消除幽灵记录
- `list_by_user` 支持游标分页，`list_session_ids` 支持 limit 截断

**Non-Goals:**
- 不修改 sessions 表 schema（无 Alembic migration）
- 不修改文件持久化格式（JSON 不变）
- 不引入跨进程锁或 JSONL 格式（属于后续独立 change）
- 不为 `session/index.py` 添加日志（index 是纯数据层，出错时由 manager 层日志覆盖）

## Decisions

### D1：日志迁移方式

`session/manager.py` 与 runtime 模块一致，模块顶部声明私有 `_logger = get_logger("session.manager")`，删除 `import structlog`。`warning` → `warn`，kwargs 风格不变（manager 已是 kwargs 风格，无 printf 转换）。

`session/index.py` 无日志，不加（纯 SQL 函数，错误由调用方捕获并记录）。

### D2：index 删除时机

删除 index 行 MUST 在文件删除**成功后**执行，不在 `try` 块之前或 `finally` 块中。理由：
- 文件删除是主操作，index 是辅助；文件删除失败时保留 index 行是正确的（index 仍与文件一致）
- 文件删除成功后 index 删除失败：index 有幽灵行，但系统在下次执行 `maybe_run_maintenance()` 时会再次尝试（文件已不存在，`_scan_sessions()` 不会返回这个 id，index 行变成永久幽灵）——因此 index 删除失败需记录 warn 日志，但不中断清理批次

选择 `delete_batch(session_ids)` 而非逐条删除：一次事务处理多行，减少 DB 往返。

### D3：分页游标选择

使用 `before_updated_at: float | None`（UNIX 时间戳）作为游标，而非 OFFSET：
- OFFSET 在大表中性能差（逐行跳过）
- `updated_at` 是已有索引列，范围查询走索引
- 客户端记录上一页最后一条的 `updated_at`，作为下一页的 `before_updated_at`

`list_session_ids` 的 limit 直接截断排序结果，已是内存操作，直接 `[:limit]` 即可（无 SQL 可用）。

## Risks / Trade-offs

- **[风险] index 删除失败导致永久幽灵行** → 每次 `maybe_run_maintenance()` 都会重新尝试扫描文件，已不存在的文件会导致 `_scan_sessions()` 不返回对应 id，幽灵行不会被再次清理。缓解：index 删除失败记录 warn 日志，便于运维发现；后续可加 "index reconciliation" 定期扫描（不在本 change 范围内）
- **[风险] updated_at 游标在并发写场景可能重复/遗漏** → session 系统本身已有写并发问题（P0-4 中处理），此处游标只用于管理控制台展示，重复/遗漏一条的影响可接受

## Migration Plan

无 schema 变更，直接部署。`list_by_user` 新参数有默认值（`limit=50, before_updated_at=None`），现有调用方（`session_admin_api`、TUI 等）行为不变。
