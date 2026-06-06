## Why

Agent 运行进程（`fleetent agent run`）重启时，正在处理中的 session（loop 尚未 `save()`）上下文状态丢失，用户重发消息会从头处理。对标 hermes-agent `suspend_recently_active()`——重启时标记近期活跃的 session 为 `resume_pending`，使其下次请求可被识别为「中断后续接」而非全新会话。本 change 建立 resume_pending 标记机制和启动扫描，为后续续接逻辑提供基础。

## What Changes

- **session_meta 表新增 resume_pending 列**：`resume_pending`（INTEGER，default 0），Alembic migration 056
- **session_admin_store 新增三个函数**：`mark_resume_pending(session_id)`、`clear_resume_pending(session_id)`、`list_resume_pending()`（返回所有 resume_pending=1 的 session_id）
- **session_admin_store 新增 scan_and_mark_recent 函数**：扫描 `session_meta` 中 `updated_at` 在最近 N 秒（默认 120）内的 session，批量标记 resume_pending
- **agent_app._start_infra 接入启动扫描**：在 `start_session_maintenance()` 之后调用 `scan_and_mark_recent`，best-effort（失败记 warn 不阻断 boot）
- **get_meta / list_meta 返回值包含 resume_pending**

## Capabilities

### New Capabilities

- `session-restart-recovery`：session 重启恢复规范——resume_pending 标记、启动扫描窗口、标记生命周期

### Modified Capabilities

（无既有行为变更——纯增量标记字段与启动钩子）

## Impact

- **修改文件**：`src/fleetent/platform/chat_management/session_admin_store.py`、`src/fleetent/runtime/agent_app.py`
- **新增文件**：Alembic migration `056_add_session_resume_pending.py`
- **无破坏性变更**：新列 default 0，启动扫描 best-effort
- **设计说明**：扫描挂在 agent_app._start_infra（session 维护实际启动点），非 server.py lifespan——platform server 已不维护 session。详见决策文档 D6。
- **范围说明**：本 change 只建立标记机制 + 启动扫描；标记的「消费」（下次请求时基于 resume_pending 续接 vs 新建）是 normalizer/loop 层的后续 wiring，不在本 change 强制实现。
