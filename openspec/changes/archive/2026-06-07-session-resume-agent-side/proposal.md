## Why

resume_pending 是最后一处 agent 运行时数据被存在 platform 的 `session_meta` 表（违反 Agent/Platform 解耦）。与 token/compaction 不同，resume_pending 是 agent 内部状态、无 observability trace 覆盖，不能简单删除——需迁移到 agent 侧。本 change 把它迁到 session 的 `.resume` 兄弟标记文件（与 `.pre-compact.json` 同模式），彻底消除最后一处 runtime→platform 依赖。

## What Changes

- **agent 侧标记文件**：`session/manager.py` 新增 `mark_resume_pending`（touch `{session_id}.resume`）、`is_resume_pending`（文件存在）、`clear_resume_pending`（删文件）、`scan_and_mark_recent_resume(window_seconds=120)`（按 session 文件 mtime 扫窗口内并标记）；导出到 `session/__init__.py`
- **agent_app**：`_start_infra` 改调 `session_mgr.scan_and_mark_recent_resume`，移除 `from platform.chat_management import session_admin_store`
- **normalizer**：resume 检测/清除改用 `session_mgr.is_resume_pending` / `clear_resume_pending`，移除 platform import
- **cleanup_expired**：删主文件后连带删 `{session_id}.resume`（best-effort）
- **platform 清理**：`session_admin_store` 删 `mark/clear/list_resume_pending`、`scan_and_mark_recent`；`_COLS`/`get_meta` fallback 删 `resume_pending`；migration 059 从 session_meta 删 `resume_pending` 列

## Capabilities

### Modified Capabilities

- `session-restart-recovery`：标记机制从 platform session_meta 改为 agent 侧 `.resume` 标记文件；扫描基于 session 文件 mtime
- `session-resume-consume`：消费改用 `session_mgr.is_resume_pending`/`clear_resume_pending`（agent 侧），不再调 platform

## Impact

- **修改文件**：`session/manager.py`、`session/__init__.py`、`runtime/agent_app.py`、`im_gateway/normalizer.py`、`platform/chat_management/session_admin_store.py`
- **新增**：migration 059（降 resume_pending 列）
- **架构收尾**：本 change 后，`runtime/`、`session/`、`im_gateway/` 不再 import `platform.chat_management`，4 处违规依赖全部清除，agent 可真正脱离 platform 独立运行
- **行为不变**：resume 标记/消费的对外语义不变，仅存储介质从 platform DB 列改为 agent 侧文件
