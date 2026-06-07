# session-compaction-checkpoint Specification

## Purpose

每次 context 压缩前将原始消息列表写入备份文件，为后续可能的压缩前状态恢复提供基础。

## Requirements

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
