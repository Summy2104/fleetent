## ADDED Requirements

### Requirement: 压缩前写入备份文件

系统 SHALL 在每次 context 压缩成功执行前，将原始消息列表原子写入 `{session_id}.pre-compact.json` 备份文件。备份 MUST 覆盖上一次压缩备份（每个 session 只保留最近一次压缩前状态）。备份写入失败 MUST 记录 warn 日志，MUST NOT 中断压缩主流程。

#### Scenario: 压缩前写入备份
- **WHEN** context 压缩即将执行（`compress()` 调用前）
- **THEN** 原始消息列表以 JSON 格式原子写入 `data/sessions/{session_id}.pre-compact.json`

#### Scenario: 备份写入失败不阻断压缩
- **WHEN** 备份文件写入过程抛出异常
- **THEN** 异常被记录为 warn 日志，压缩流程正常继续，session 主文件不受影响

#### Scenario: 多次压缩只保留最近一次备份
- **WHEN** 同一 session 发生第二次压缩
- **THEN** 新备份文件覆盖旧备份，`{session_id}.pre-compact.json` 始终对应最近一次压缩前的状态

### Requirement: 压缩完成后更新 session_meta 压缩记录

系统 SHALL 在 context 压缩完成后，更新 session_meta 表中该 session 的压缩记录字段：`last_compaction_at`（压缩完成时间）、`messages_before_compaction`（压缩前消息数）、`messages_after_compaction`（压缩后消息数）、`compaction_summary_preview`（摘要文本前 200 字符）。meta 更新失败 MUST 记录 warn 日志，MUST NOT 影响压缩结果和 session 持久化。

#### Scenario: 压缩后 meta 记录压缩信息
- **WHEN** context 压缩成功完成
- **THEN** session_meta 表中该 session 的 `last_compaction_at`、`messages_before_compaction`、`messages_after_compaction`、`compaction_summary_preview` 被更新

#### Scenario: meta 更新失败不回滚压缩结果
- **WHEN** session_meta 更新抛出异常
- **THEN** 异常被记录为 warn 日志，压缩后的消息列表照常返回给调用方，session 持久化不受影响

### Requirement: session_meta 表新增压缩记录列

`sessions` 表（session_meta）SHALL 新增四列：`last_compaction_at`（REAL，NULL）、`messages_before_compaction`（INTEGER，NULL）、`messages_after_compaction`（INTEGER，NULL）、`compaction_summary_preview`（TEXT，NULL，最多 200 字符）。现有 session 这四列默认为 NULL，表示从未经历过压缩。

#### Scenario: 新列允许 NULL 且不影响现有 session
- **WHEN** 系统升级后查询一个从未压缩过的历史 session 的元数据
- **THEN** 四个压缩相关列返回 NULL，不报错，其余字段不受影响

#### Scenario: Alembic migration 向现有表添加列
- **WHEN** 运行数据库 migration
- **THEN** `sessions` 表新增四列，现有行的新列值为 NULL
