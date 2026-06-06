## Why

`resume_pending` 标记机制已建立（session-restart-recovery）：agent 启动时标记重启前活跃的 session。但消费端缺失——标记被写入后无人检测、无人清除，导致标记永久残留、无运营可见性。本 change 在 IM 消息处理路径接入消费闭环：检测到 resume_pending 时记录日志并清除标记。

## What Changes

- **normalizer.py 接入 resume 检测**：在 `session_mgr.load(session_id)` 之后、跑 agent loop 之前，调 `session_admin_store.get_meta(session_id)` 检测 `resume_pending`
- **消费闭环**：若 `resume_pending == 1`，记录 `_logger.info("session_resumed", session_id=...)` 并调 `session_admin_store.clear_resume_pending(session_id)`，使标记不再永久残留
- **best-effort**：整段用 try/except 包裹，检测/清除失败不阻断消息处理

## Capabilities

### New Capabilities

- `session-resume-consume`：resume_pending 标记的消费规范——检测时机、日志、清除闭环、容错

## Impact

- **修改文件**：`src/fleetent/im_gateway/normalizer.py`
- **无契约变更**：仅在已有 load→run→save 流程中插入检测段
- **行为说明**：本 change 实现「标记消费闭环」（识别+清除），使重启恢复机制有完整生命周期。更丰富的续接语义（如恢复中断上下文）依赖已落盘的 session 文件（load 已读回完整历史），不需要额外逻辑——resume_pending 主要用于「识别这是中断恢复」的运营可见性
- **范围**：仅 IM 路径（normalizer）；CLI（run_sync）一次性进程不涉及重启恢复
