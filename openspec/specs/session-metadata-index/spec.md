# session-metadata-index Specification

## Purpose
TBD - created by archiving change session-metadata-index. Update Purpose after archive.
## Requirements
### Requirement: session 元数据存储

系统 SHALL 在 `users.db` 的 `sessions` 表中为每个 session 维护轻量元数据，至少包含 `session_id`、`user_id`、`created_at`、`updated_at`（最后活跃时间）、`message_count`、`agent_name`。元数据 MUST 存于数据库表，与 session 的消息 JSON 文件物理分离，MUST NOT 增加消息文件本身的体积。

#### Scenario: 首次记录创建元数据
- **WHEN** 某 session 首次被记录活跃
- **THEN** `sessions` 表新增一行，`created_at` 与 `updated_at` 均为当前时间，`message_count` 为当前消息数

#### Scenario: 元数据与消息文件分离存储
- **WHEN** 写入 session 元数据
- **THEN** 元数据写入 `users.db` 的 `sessions` 表，session 消息 JSON 文件内容不因此增加元数据字段

### Requirement: 活跃时元数据 upsert 更新

记录活跃函数 SHALL 对同一 `session_id` 执行 upsert：已存在时 MUST 保留原 `created_at`、刷新 `updated_at` 为当前时间、更新 `message_count`，不存在时 MUST 新建记录。

#### Scenario: 再次活跃更新最后活跃时间
- **WHEN** 一个已存在元数据的 session 再次被记录活跃
- **THEN** `created_at` 保持首次时间不变，`updated_at` 刷新为当前时间，`message_count` 更新为最新消息数

### Requirement: session 元数据查询

系统 SHALL 提供按 session 与按 user 的元数据查询。`get(session_id)` MUST 在不存在时返回空结果；`list_by_user(user_id)` MUST 返回该 user 的全部 session 元数据并按最后活跃时间倒序排列。

#### Scenario: 查询单个 session 元数据
- **WHEN** 以存在的 `session_id` 查询元数据
- **THEN** 返回该 session 的元数据；以不存在的 `session_id` 查询时返回空结果

#### Scenario: 按 user 列出 session 并按活跃时间倒序
- **WHEN** 查询某 user 的全部 session
- **THEN** 返回该 user 的 session 元数据列表，最近活跃的 session 排在最前

### Requirement: 全系统统计查询

系统 SHALL 提供全系统聚合统计：session 总数与全部 session 的消息总数。

#### Scenario: 统计 session 总数与消息总数
- **WHEN** 调用全系统统计查询
- **THEN** 返回当前 `sessions` 表中的 session 总数，以及所有 session 的 `message_count` 之和

### Requirement: 元数据故障不破坏消息持久化

session 消息持久化 SHALL 在元数据更新之前完成；元数据更新失败 MUST NOT 回滚或破坏已成功写入的消息文件，且 MUST 记录日志。

#### Scenario: 索引更新失败不影响消息写入
- **WHEN** session 消息文件已原子写成功，但随后的元数据更新抛出异常
- **THEN** 消息文件保持已写入状态不被回滚，异常被记录为日志，`save()` 不向上抛出该异常

