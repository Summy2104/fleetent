## ADDED Requirements

### Requirement: Knowledge-base reflection report public API
reflection SHALL 提供只读 Knowledge Base 质量报告 API，用于发现 KB 缺口和检索质量问题。

#### Scenario: KB reflection API is importable
- **WHEN** 调用方从 `fleetent.intelligence.reflection` 导入 `KnowledgeBaseReflectionReport`、`KnowledgeBaseReflectionFinding` 和 `run_kb_reflection_report`
- **THEN** 导入成功

#### Scenario: KB reflection report contains required fields
- **WHEN** `run_kb_reflection_report()` 返回 report
- **THEN** report 包含 id、scope、time_window、findings、created_at 和 signal_summary

### Requirement: Knowledge-base reflection is read-only
KB reflection SHALL 只生成报告和 findings，不自动修改 Knowledge Base。

#### Scenario: Report does not mutate KB
- **WHEN** KB reflection 发现 missing 或 stale finding
- **THEN** 系统不创建、更新、删除或归档 KB document
- **AND** 不触发 connector sync

#### Scenario: Report does not create KB proposal
- **WHEN** KB reflection 生成 finding
- **THEN** 系统不创建 KB mutation proposal

### Requirement: Knowledge-base reflection inputs use public APIs
KB reflection SHALL 只通过 observability 和 knowledge-base public API 读取信号。

#### Scenario: Observability signal uses public API
- **WHEN** KB reflection 读取 trace、source attribution 或 retrieval event
- **THEN** 系统调用 observability public API

#### Scenario: Knowledge-base signal uses public API
- **WHEN** KB reflection 读取 connector status、search 或 graph signal
- **THEN** 系统调用 knowledge-base public API
- **AND** 不直接查询 knowledge-base owned tables

### Requirement: Knowledge-base reflection finding types
KB reflection SHALL 支持固定 finding 类型，并为每条 finding 保存 evidence 和 recommendation。

#### Scenario: Missing knowledge finding
- **WHEN** 同类 query 多次出现 zero-result、低 source attribution 或低置信检索
- **THEN** report 包含 `type="missing_knowledge"` finding

#### Scenario: Stale document finding
- **WHEN** trace 或 connector metadata 显示文档可能过期
- **THEN** report 包含 `type="stale_document"` finding

#### Scenario: Low retrieval quality finding
- **WHEN** 同一 topic 多次出现低分结果、用户纠正或 source attribution 缺失
- **THEN** report 包含 `type="low_retrieval_quality"` finding

#### Scenario: Connector sync issue finding
- **WHEN** connector latest status 显示 failed、stale 或连续失败
- **THEN** report 包含 `type="connector_sync_issue"` finding

#### Scenario: Entity graph gap finding
- **WHEN** 关系型 query 缺少 graph evidence 或 entity/graph 覆盖不足
- **THEN** report 包含 `type="entity_graph_gap"` finding

#### Scenario: Finding includes evidence
- **WHEN** KB reflection 返回 finding
- **THEN** finding 包含 severity、affected_resource、evidence_refs 和 recommendation

### Requirement: Knowledge-base reflection persistence
系统 SHALL 持久化 KB reflection reports，且不得保存完整用户 transcript 或完整文档正文。

#### Scenario: Migration creates KB reflection reports
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `kb_reflection_reports` 表

#### Scenario: Persisted payload is redacted
- **WHEN** KB reflection report 被保存
- **THEN** payload 只包含 finding summary、evidence ids、短摘要和 metadata
- **AND** 不包含完整用户对话 transcript 或完整文档正文

### Requirement: Knowledge-base reflection evaluation
系统 SHALL 提供 deterministic evaluation，验证 KB reflection findings 和 payload redaction。

#### Scenario: Expected KB findings are validated
- **WHEN** evaluation fixture 运行
- **THEN** expected findings 出现在 report 中

#### Scenario: Forbidden KB findings are rejected
- **WHEN** evaluation fixture 运行
- **THEN** forbidden findings 不出现在 report 中

#### Scenario: KB unavailable does not fail report
- **WHEN** knowledge-base public API 不可用或未启用
- **THEN** report 返回 insufficient signal finding 或 signal summary
- **AND** 不抛出运行时异常
