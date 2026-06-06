## Why

Context 压缩是单向不可逆操作：`compress()` 将中段消息替换为 LLM 摘要后，原始消息永久丢失。摘要质量差、LLM 生成偏离、或用户需要回溯历史时，没有任何恢复手段。对标 openclaw（`SessionCompactionCheckpoint`）和 opencode（`revert` 字段）均已实现压缩检查点；这是生产环境 session 可靠性的基础能力。

## What Changes

- **压缩前写入备份文件**：`compress()` 执行前将原始消息列表原子写入 `data/sessions/{session_id}.pre-compact.json`；每次压缩覆盖前一次（只保留最近一次压缩前状态）
- **session_meta 表新增压缩记录列**：`last_compaction_at`（REAL）、`messages_before_compaction`（INTEGER）、`messages_after_compaction`（INTEGER）、`compaction_summary_preview`（TEXT，摘要前 200 字符）；通过 Alembic migration 添加，允许 NULL
- **session/manager.py 新增两个函数**：`write_compaction_checkpoint(session_id, messages)` 写备份文件；`delete_compaction_checkpoint(session_id)` 删除备份文件（供 cleanup_expired 调用）
- **cleanup_expired 同步删除备份文件**：删除 `session_id.json` 后，同时尝试删除 `session_id.pre-compact.json`（若存在）
- **session_admin_store 新增 update_compaction_meta 函数**：压缩完成后更新 session_meta 四个新列
- **所有新操作均为 best-effort**：备份写失败或 meta 更新失败均记录 warn 日志，不中断压缩主流程

## Capabilities

### New Capabilities

- `session-compaction-checkpoint`：session 压缩检查点规范——备份文件生命周期、meta 记录字段、best-effort 语义

### Modified Capabilities

- `session-persistence`：`compress()` 执行前 SHALL 写入压缩前备份文件；`cleanup_expired()` SHALL 同步删除对应备份文件

## Impact

- **修改文件**：`src/fleetent/runtime/context.py`、`src/fleetent/session/manager.py`、`src/fleetent/platform/chat_management/session_admin_store.py`
- **新增文件**：Alembic migration（`migrations/versions/0NN_add_session_compaction_meta.py`）
- **无破坏性变更**：新列允许 NULL，现有 session 无影响；备份文件不影响主 session 文件读写
- **磁盘占用**：每个有过压缩的 session 多一份 `.pre-compact.json`，体积约等于压缩前消息体积；TTL 清理时自动回收
