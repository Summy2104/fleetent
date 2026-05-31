# reflection Specification

## Purpose
Generate structured self-improvement reports from observability traces and read-only memory
signals without automatically applying changes to memory, skills, or knowledge-base content.

## Requirements
### Requirement: Reflection report public API
系统 SHALL 提供 `ReflectionReport`、`ReflectionFinding` 和 `run_reflection(scope)` public API，
用于生成结构化自我改进建议报告。

#### Scenario: Public API is importable
- **WHEN** 调用方从 reflection 模块导入 `ReflectionReport`、`ReflectionFinding` 和 `run_reflection`
- **THEN** 导入成功

#### Scenario: Report contains required fields
- **WHEN** `run_reflection()` 返回 report
- **THEN** report 包含 id、scope、time_window、findings 和 created_at

### Requirement: Trace-based analysis input
reflection SHALL 只通过 observability public API 读取 agent run history。

#### Scenario: Reflection queries traces through public API
- **WHEN** `run_reflection()` 执行
- **THEN** 系统调用 `observability.query_trace_events()` 读取指定 scope 和 time window 的 trace events

#### Scenario: Empty traces produce empty report
- **WHEN** 查询范围内没有 trace events
- **THEN** `run_reflection()` 返回 findings 为空的 report
- **AND** 不抛出异常

### Requirement: Memory input is read-only
reflection SHALL 可以读取 memory-layer 信号用于分析，但本阶段不得自动修改 memory。

#### Scenario: Memory signal can be used
- **WHEN** memory-layer 返回与 trace 相关的 memory 信号
- **THEN** reflection 可以将其用于 finding 生成

#### Scenario: Reflection does not write memory
- **WHEN** `run_reflection()` 生成 memory 相关 finding
- **THEN** 系统不创建、更新或删除 `memory_items`

### Requirement: Foundation finding types
reflection SHALL 在第一阶段支持 `memory_candidate`、`memory_conflict` 和 `skill_opportunity`
三类 finding。

#### Scenario: Memory candidate finding
- **WHEN** trace events 中重复出现同一用户事实，且该事实尚未稳定进入 memory
- **THEN** report 包含 `type="memory_candidate"` 的 finding

#### Scenario: Memory conflict finding
- **WHEN** trace events 或 memory 信号中出现相互矛盾的用户事实
- **THEN** report 包含 `type="memory_conflict"` 的 finding

#### Scenario: Skill opportunity finding
- **WHEN** trace events 中反复出现同类任务模式
- **THEN** report 包含 `type="skill_opportunity"` 的 finding

### Requirement: Reflection report persistence
系统 SHALL 可以保存 reflection report，且保存内容不得包含完整 trace transcript。

#### Scenario: Migration creates reflection_reports
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `reflection_reports` 表

#### Scenario: Persisted report omits raw transcript
- **WHEN** report 被保存
- **THEN** 保存的 payload 包含 finding summary、evidence ids 和 metadata
- **AND** 不包含完整用户对话 transcript

### Requirement: No automatic application
reflection foundation SHALL 只生成建议，不自动应用建议。

#### Scenario: Skill opportunity does not write skill files
- **WHEN** report 包含 `skill_opportunity` finding
- **THEN** 系统不创建、更新或删除 `skills/` 文件

#### Scenario: Knowledge-base is not required
- **WHEN** knowledge-base 未实现或未启用
- **THEN** `run_reflection()` 仍可基于 traces 和 memory 返回 report
