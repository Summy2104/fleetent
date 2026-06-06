# session-restart-recovery Specification

## Purpose
Mark sessions active just before an agent restart as resume_pending so interrupted conversations can be resumed.

## Requirements

### Requirement: session_meta 表新增 resume_pending 列

`session_meta` 表 SHALL 新增 `resume_pending`（INTEGER，default 0）列，通过 Alembic migration 添加。现有行默认为 0。

#### Scenario: migration 添加 resume_pending 列
- **WHEN** 运行数据库 migration
- **THEN** `session_meta` 表新增 `resume_pending` 列，现有行值为 0

### Requirement: resume_pending 标记读写接口

系统 SHALL 提供 `mark_resume_pending(session_id)`、`clear_resume_pending(session_id)`、`list_resume_pending()` 三个函数。`mark` 在行不存在时先创建；`clear` 将标记置 0；`list` 返回所有 `resume_pending=1` 的 session_id 列表。

#### Scenario: 标记并查询 resume_pending
- **WHEN** 调用 `mark_resume_pending("s1")` 后调用 `list_resume_pending()`
- **THEN** 返回列表包含 "s1"

#### Scenario: 清除 resume_pending
- **WHEN** 对已标记的 session 调用 `clear_resume_pending`
- **THEN** 该 session 不再出现在 `list_resume_pending()` 返回值中

#### Scenario: mark 首次自动创建行
- **WHEN** 对 session_meta 中无行的 session 调用 `mark_resume_pending`
- **THEN** 自动创建元数据行并置 resume_pending=1，不报错

### Requirement: 启动扫描标记近期活跃 session

系统 SHALL 提供 `scan_and_mark_recent(window_seconds=120)` 函数，扫描 `session_meta` 中 `updated_at` 在最近 `window_seconds` 秒内的 session，批量标记为 resume_pending，返回被标记的 session_id 列表。

#### Scenario: 标记窗口内活跃 session
- **WHEN** 一个 session 的 updated_at 在最近 120 秒内，调用 `scan_and_mark_recent()`
- **THEN** 该 session 被标记 resume_pending，并出现在返回列表中

#### Scenario: 不标记窗口外的旧 session
- **WHEN** 一个 session 的 updated_at 早于 120 秒前，调用 `scan_and_mark_recent()`
- **THEN** 该 session 不被标记，不在返回列表中

### Requirement: agent 启动时执行恢复扫描

agent 运行进程 SHALL 在 `_start_infra` 启动 session 维护任务后调用 `scan_and_mark_recent`。该调用 MUST 为 best-effort——扫描失败 MUST 记 warn 日志，MUST NOT 阻断 agent boot。

#### Scenario: 启动扫描失败不阻断 boot
- **WHEN** agent 启动时恢复扫描抛出异常
- **THEN** 异常被记录为 warn 日志，agent boot 继续完成
