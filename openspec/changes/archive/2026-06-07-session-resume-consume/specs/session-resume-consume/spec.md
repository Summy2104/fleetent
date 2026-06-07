## ADDED Requirements

### Requirement: IM 消息处理时消费 resume_pending 标记

IM 消息处理路径（normalizer）SHALL 在加载 session 历史后、运行 agent loop 前，检测该 session 的 `resume_pending` 标记。当标记为 1 时，系统 MUST 记录一条 `session_resumed` info 日志，并清除该标记（`clear_resume_pending`），使标记不永久残留。检测与清除 MUST 为 best-effort——失败 MUST 记 warn 日志，MUST NOT 阻断消息处理。

#### Scenario: 检测到 resume_pending 时记录并清除
- **WHEN** 一条 IM 消息到达，其 session 的 `resume_pending` 为 1
- **THEN** 系统记录 `session_resumed` 日志，调用 `clear_resume_pending`，随后正常处理消息

#### Scenario: 无 resume_pending 时正常处理
- **WHEN** 一条 IM 消息到达，其 session 的 `resume_pending` 为 0
- **THEN** 不记录 resumed 日志、不调用 clear，消息正常处理

#### Scenario: 标记消费失败不阻断消息处理
- **WHEN** 检测或清除 resume_pending 过程中抛出异常
- **THEN** 异常被记录为 warn 日志，消息处理继续不受影响
