# session-restart-recovery Specification

## Purpose
Mark sessions active just before an agent restart as resume_pending so interrupted conversations can be resumed.

## Requirements

### Requirement: resume_pending 标记读写接口

系统 SHALL 在 agent 侧（`session/manager`）提供 `mark_resume_pending(session_id)`、`is_resume_pending(session_id)`、`clear_resume_pending(session_id)` 三个函数，以 session 的 `.resume` 兄弟标记文件（`{session_id}.resume`）表示状态：`mark` 创建该文件，`is` 返回文件是否存在，`clear` 删除该文件（不存在时静默）。MUST NOT 依赖 platform 或任何数据库表。

#### Scenario: 标记并查询 resume
- **WHEN** 调用 `mark_resume_pending("s1")` 后调用 `is_resume_pending("s1")`
- **THEN** 返回 True，且 `{s1}.resume` 文件存在

#### Scenario: 清除 resume
- **WHEN** 对已标记的 session 调用 `clear_resume_pending`
- **THEN** `.resume` 文件被删除，`is_resume_pending` 返回 False

#### Scenario: 清除不存在的标记不报错
- **WHEN** 对未标记的 session 调用 `clear_resume_pending`
- **THEN** 调用正常返回，不抛异常

### Requirement: 启动扫描标记近期活跃 session

系统 SHALL 在 agent 侧提供 `scan_and_mark_recent_resume(window_seconds=120)`，按 session 文件的最后活跃时间（mtime）扫描，对处于最近 `window_seconds` 秒内的 session 创建 `.resume` 标记，返回被标记的 session_id 列表。MUST 基于 session 文件 mtime，MUST NOT 查询 platform 数据表。

#### Scenario: 标记窗口内活跃 session
- **WHEN** 一个 session 文件 mtime 在最近 120 秒内，调用 `scan_and_mark_recent_resume()`
- **THEN** 该 session 被创建 `.resume` 标记，并出现在返回列表中

#### Scenario: 不标记窗口外的旧 session
- **WHEN** 一个 session 文件 mtime 早于 120 秒前
- **THEN** 该 session 不被标记，不在返回列表中

### Requirement: agent 启动时执行恢复扫描

agent 运行进程 SHALL 在 `_start_infra` 启动 session 维护任务后调用 `session_mgr.scan_and_mark_recent_resume`（agent 侧，不调用 platform）。该调用 MUST 为 best-effort——扫描失败 MUST 记 warn 日志，MUST NOT 阻断 agent boot。

#### Scenario: 启动扫描失败不阻断 boot
- **WHEN** agent 启动时恢复扫描抛出异常
- **THEN** 异常被记录为 warn 日志，agent boot 继续完成

#### Scenario: 启动扫描不依赖 platform
- **WHEN** agent 在无 platform、无 session_meta 表的环境下启动
- **THEN** 恢复扫描正常工作（基于 session 文件 mtime），不因缺少 platform 表而失败
