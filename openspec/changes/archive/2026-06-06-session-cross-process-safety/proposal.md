## Why

当前 `session_lock()` 仅用进程内 `asyncio.Lock`，只能串行化同一进程内的协程。当 CLI（`run_sync`）与 server 进程、或多个 server worker 并发写同一 session 文件时，没有跨进程保护：两个进程可能同时读到旧版本、各自修改、后写者覆盖前写者，导致消息丢失。对标 openclaw（`.lock` 文件 + PID 校验）和 hermes-agent（SQLite WAL + 应用层重试）均有跨进程并发安全机制。

## What Changes

- **session_lock 升级为双层锁**：在现有进程内 `asyncio.Lock` 外层，增加基于 `fcntl.flock()` 的文件级排他锁（`.lock` 文件），实现跨进程串行化
- **锁文件路径**：`data/sessions/{session_id}.lock`，与主 session 文件同目录约定（支持含 `/` 的 session_id）
- **锁获取顺序**：先获取文件锁（跨进程），再获取 asyncio.Lock（同进程协程），保证两层语义不冲突
- **锁文件不纳入 TTL 清理与扫描**：`cleanup_expired`、`enforce_capacity`、`_scan_sessions`、`list_session_ids` 跳过 `.lock` 文件
- **平台兼容性**：使用 POSIX `fcntl`（Linux/macOS）；模块顶部条件导入，非 POSIX 环境降级为仅 asyncio.Lock（记录一次 warn）

## Capabilities

### New Capabilities

- `session-cross-process-safety`：session 跨进程并发安全规范——文件锁机制、双层锁顺序、锁文件生命周期、平台降级

### Modified Capabilities

- `session-persistence`：`Session isolation` requirement 从"进程内 asyncio.Lock"扩展为"跨进程文件锁 + 进程内 asyncio.Lock 双层"

## Impact

- **修改文件**：`src/fleetent/session/manager.py`（session_lock、_scan_sessions、list_session_ids、cleanup_expired、enforce_capacity）
- **新增依赖**：无（`fcntl` 为 Python 标准库）
- **无破坏性变更**：`session_lock` 接口不变，调用方无感知；锁文件对现有 session 透明
- **平台限制**：跨进程锁仅在 POSIX 生效；Windows 部署降级为进程内锁（fleetent 定位 Linux 部署，可接受）
