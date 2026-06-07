## Why

内置 `todo` 工具用进程内模块级 dict（`_todo_store`），进程重启即丢、无完成状态、上下文压缩会丢失、且违反「禁全局可变状态」。长任务（企业多步工单）需要可持久、带状态的待办清单，且必须纯 agent 侧（不依赖 platform）。

## What Changes

- **todo 工具升级为状态机**：条目由纯字符串升级为 `{id, text, status}`（status ∈ `pending` / `in_progress` / `completed`，至多一个 `in_progress`）；action 由 `set`/`get`/`clear` 扩展为 `set` / `update`（按 id 改状态）/ `get` / `clear`。
- **持久化到 agent 侧兄弟文件**：todo 权威状态存 `{session_id}.todo`（JSON 内容），跨进程重启存活；与 `.pre-compact.json` / `.resume` / `.tool_outputs` 同模式。
- **session 维护连带清理**：`cleanup_expired()` 删除过期 session 主文件时连带删除 `{session_id}.todo`。
- **移除内存实现**：废弃模块级 `_todo_store`（修「禁全局可变状态」隐患）。
- `session/manager.py` 新增 `read_todo` / `write_todo`（原子 `tmp→rename`）/ `clear_todo` 持久化 helper，导出到 `session/__init__.py`。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `builtin-interaction-tools`: todo 需求从「内存、`set`/`get`/`clear`、不持久化、session 结束即释放」改为「状态机、`set`/`update`/`get`/`clear`、agent 侧兄弟文件持久化、跨进程重启存活」。
- `session-ttl-cleanup`: 过期 session 一次性清理需求新增「成功删除主文件后连带删除 `{session_id}.todo` 兄弟文件（best-effort）」。

## Impact

- **修改文件**：`src/fleetent/tools/interaction_tools.py`（todo 工具重写）、`src/fleetent/session/manager.py`（新增 todo 持久化 helper + cleanup 连带删除）、`src/fleetent/session/__init__.py`（导出 helper）。
- **行为变化**：todo 现跨进程重启存活（原内存版不存活）；action 新增 `update`；条目结构带 `status`（向后兼容：`set` 仍接受 `list[str]`，字符串项自动赋 `id` + `pending`）。
- **解耦合规**：纯 agent-side，零 platform 依赖，不写 platform `session_meta` 表，不写 session JSON `meta`，不引入 DB 表；持久化兄弟文件**原子写、不取 `session_lock`**（避免与 IM 路径整 run 持有的 session_lock 死锁）。
- 无 API / 外部依赖变更，无新依赖。
