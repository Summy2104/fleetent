# channel-agent-binding Delta

## REMOVED Requirements

### Requirement: Channel-to-agent binding storage
**Reason**: `channel_agents` 表 descope——一 agent 一 bot 模型下消息由连接器连接定 agent，按渠道路由 runtime 从不消费；整条 DB→agent file→runtime 链端到端未接。

### Requirement: Channel binding takes priority over user binding in agent lookup
**Reason**: 渠道/用户文件绑定路由已废（runtime 走连接器=agent）。该查找顺序的彻底重写归 IM 访问模型阶段 3。

### Requirement: channel_agents carries bound_version_id audit column
**Reason**: 随 `channel_agents` 表移除；`bound_version_id` 为无 FK 的休眠列、无生产消费。

## ADDED Requirements

### Requirement: Management DB excludes channel-agent binding capability
The management database MUST NOT expose a `channel_agents` table or any direct channel-to-agent
binding API surface.

#### Scenario: Head schema and admin surface exclude channel bindings
- **WHEN** management DB migrations are applied to head and the admin surface is exercised
- **THEN** no `channel_agents` table exists
- **AND** no channel binding CRUD endpoint or CLI command is available
