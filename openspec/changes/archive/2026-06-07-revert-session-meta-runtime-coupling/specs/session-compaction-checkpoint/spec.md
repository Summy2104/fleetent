## REMOVED Requirements

### Requirement: 压缩完成后更新 session_meta 压缩记录

**Reason**: 把 agent 运行时压缩统计写入 platform 的 `session_meta` 表违反 Agent/Platform 解耦（CLAUDE.md 不可逾越规则）。压缩统计已由 observability trace（`context.py` 的 `log_compression`）覆盖。

**Migration**: 不再写 session_meta；需要压缩统计时读 observability trace。`.pre-compact.json` 备份文件机制不变。

### Requirement: session_meta 表新增压缩记录列

**Reason**: 上述 requirement 移除后，session_meta 的 `last_compaction_at` / `messages_before_compaction` / `messages_after_compaction` / `compaction_summary_preview` 成为无写入方的死列。

**Migration**: migration 058 从 session_meta 删除这四列。
