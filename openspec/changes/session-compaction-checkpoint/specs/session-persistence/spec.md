## ADDED Requirements

### Requirement: 压缩检查点备份文件管理

系统 SHALL 提供 `write_compaction_checkpoint(session_id, messages)` 和 `delete_compaction_checkpoint(session_id)` 两个函数管理压缩备份文件。`write_compaction_checkpoint` MUST 使用原子写（tmp → rename），`delete_compaction_checkpoint` MUST 静默处理文件不存在的情况。

#### Scenario: 写入压缩检查点
- **WHEN** 调用 `write_compaction_checkpoint(session_id, messages)`
- **THEN** messages 以 JSON 格式原子写入 `data/sessions/{session_id}.pre-compact.json`

#### Scenario: 删除不存在的检查点不报错
- **WHEN** 调用 `delete_compaction_checkpoint(session_id)` 且备份文件不存在
- **THEN** 函数正常返回，不抛出异常

## MODIFIED Requirements

### Requirement: 过期 session 一次性清理

清理函数 `cleanup_expired()` SHALL 扫描 session 目录，删除所有过期 session 文件，并返回被删除的 session_id 列表。清理 MUST 不影响未过期的 session，MUST 不删除原子写产生的 `.json.tmp` 临时文件，MUST 不将 `.pre-compact.json` 备份文件纳入过期判定（备份文件跟随主文件删除，不独立判断 TTL）。清理成功删除主文件后 MUST 同步删除对应的 `.pre-compact.json` 备份文件（若存在），备份删除失败静默处理。清理成功删除文件后 MUST 同步删除 `sessions` 表中对应的 index 行；index 行删除失败 MUST 记录 warn 日志，MUST NOT 中断整批清理。

#### Scenario: 清理跳过备份文件的过期判定
- **WHEN** `cleanup_expired()` 扫描 session 目录时遇到 `.pre-compact.json` 文件
- **THEN** 该文件不被纳入 TTL 过期判定，不被直接删除

#### Scenario: 清理主文件时同步删除备份文件
- **WHEN** `cleanup_expired()` 成功删除某 session 的主文件 `{session_id}.json`
- **THEN** 对应的 `{session_id}.pre-compact.json` 若存在则被同步删除

#### Scenario: 备份文件删除失败静默处理
- **WHEN** 主文件删除成功但备份文件删除失败
- **THEN** 失败被静默处理，不记录 warn 日志，不中断清理批次
