# session-resume-consume Specification

## Purpose
Consume the resume_pending flag on the IM message path: detect on session load, log once, and clear so it does not linger.

## Requirements

### Requirement: IM 消息处理时消费 resume_pending 标记

IM 消息处理路径（normalizer）SHALL 在加载 session 历史后、运行 agent loop 前，通过 agent 侧 `session_mgr.is_resume_pending(session_id)` 检测该 session 的 resume 标记（`.resume` 文件）。命中时系统 MUST 记录一条 `session_resumed` info 日志，并调 `session_mgr.clear_resume_pending(session_id)` 清除标记。检测与清除 MUST 为 best-effort——失败 MUST 记 warn 日志，MUST NOT 阻断消息处理。MUST NOT 调用 platform。

#### Scenario: 检测到 resume 标记时记录并清除
- **WHEN** 一条 IM 消息到达，其 session 存在 `.resume` 标记
- **THEN** 系统记录 `session_resumed` 日志，调用 `session_mgr.clear_resume_pending`，随后正常处理消息

#### Scenario: 无 resume 标记时正常处理
- **WHEN** 一条 IM 消息到达，其 session 无 `.resume` 标记
- **THEN** 不记录 resumed 日志、不调用 clear，消息正常处理

#### Scenario: 标记消费失败不阻断消息处理
- **WHEN** 检测或清除过程中抛出异常
- **THEN** 异常被记录为 warn 日志，消息处理继续不受影响

#### Scenario: 消费不依赖 platform
- **WHEN** agent 在无 platform 环境下处理 IM 消息
- **THEN** resume 检测/清除基于 agent 侧 `.resume` 文件正常工作，不调用 platform
