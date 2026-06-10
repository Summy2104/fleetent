# session-metadata-index Specification

## Purpose
TBD - created by archiving change session-metadata-index. Update Purpose after archive.
## Requirements
### Requirement: session 元数据存储

系统 SHALL 在 **per-agent `agent_state.db`**（由 `agent_scope(tenant, agent_id)` 解析，见 `tenant-scoped-db-routing`）的 `sessions` 表中为每个 session 维护轻量元数据，至少包含 `session_id`、`user_id`、`created_at`、`updated_at`（最后活跃时间）、`message_count`、`agent_name`。元数据 MUST 存于数据库表，与 session 的消息 JSON 文件物理分离，MUST NOT 增加消息文件本身的体积。`session/index.py` 的 schema SHALL 经 per-agent 库的**嵌入式 forward-only 迁移（Y，migrate-on-open）**建立，**SHALL NOT** 再以 `ensure_schema`-into-global（`fleetent.db.create_database` + `ensure_schema`）建于 `DATABASE_URL` 单库；连接经 `agent_scope` 取得，SHALL NOT 使用裸 `sqlite3.connect`，SHALL NOT 写入独立 `users.db`。

#### Scenario: 首次记录创建元数据
- **WHEN** 某 session 首次被记录活跃
- **THEN** per-agent `agent_state.db` 的 `sessions` 表新增一行，`created_at` 与 `updated_at` 均为当前时间，`message_count` 为当前消息数

#### Scenario: 元数据存于 per-agent 库且与消息文件分离

- **WHEN** 写入 session 元数据
- **THEN** 元数据写入 `agent_scope` 解析的 per-agent `agent_state.db` 的 `sessions` 表
- **AND** 不创建或写入 `users.db`
- **AND** session 消息 JSON 文件内容不因此增加元数据字段

#### Scenario: 经 agent_scope + Y 访问

- **WHEN** `session/index.py` 读写元数据
- **THEN** 连接经 `agent_scope(tenant, agent_id)` 取得、schema 经嵌入式 Y 建立，模块内不出现 `sqlite3.connect`、不走 `ensure_schema`-into-global

### Requirement: 活跃时元数据 upsert 更新

记录活跃函数 SHALL 对同一 `session_id` 执行 upsert：已存在时 MUST 保留原 `created_at`、刷新 `updated_at` 为当前时间、更新 `message_count`，不存在时 MUST 新建记录。

#### Scenario: 再次活跃更新最后活跃时间
- **WHEN** 一个已存在元数据的 session 再次被记录活跃
- **THEN** `created_at` 保持首次时间不变，`updated_at` 刷新为当前时间，`message_count` 更新为最新消息数

### Requirement: session 元数据批量删除

系统 SHALL 提供 `delete(session_id)` 和 `delete_batch(session_ids)` 函数，删除 `sessions` 表中指定 session 的元数据行。`delete_batch` MUST 在单个事务中删除所有指定行。删除不存在的 session_id MUST NOT 报错（幂等）。

#### Scenario: 删除单行元数据
- **WHEN** 以存在的 `session_id` 调用 `delete(session_id)`
- **THEN** `sessions` 表中该行被删除，后续 `get(session_id)` 返回 None

#### Scenario: 批量删除多行元数据
- **WHEN** 以多个 `session_id` 调用 `delete_batch(session_ids)`
- **THEN** 所有指定行在单个事务中被删除

#### Scenario: 删除不存在的 session_id 幂等
- **WHEN** 以不存在的 `session_id` 调用 `delete` 或 `delete_batch`
- **THEN** 调用正常返回，不抛出异常，表数据不受影响

### Requirement: session 元数据查询

系统 SHALL 提供按 session 与按 user 的元数据查询。`get(session_id)` MUST 在不存在时返回 None；`list_by_user(user_id, limit=50, before_updated_at=None)` MUST 返回该 user 的 session 元数据，按最后活跃时间倒序排列，支持游标分页：当 `before_updated_at` 非 None 时，MUST 只返回 `updated_at < before_updated_at` 的记录；`limit` MUST 限制返回行数上限，默认 50。

#### Scenario: 查询单个 session 元数据
- **WHEN** 以存在的 `session_id` 查询元数据
- **THEN** 返回该 session 的元数据；以不存在的 `session_id` 查询时返回 None

#### Scenario: 按 user 列出 session 并按活跃时间倒序（默认分页）
- **WHEN** 调用 `list_by_user(user_id)` 不传游标参数
- **THEN** 返回该 user 最近 50 条 session 元数据，最近活跃的排在最前

#### Scenario: 游标分页获取下一页
- **WHEN** 以上一页最后一条的 `updated_at` 作为 `before_updated_at` 调用 `list_by_user`
- **THEN** 返回 `updated_at` 早于该游标值的下一页记录，不重复上一页内容

#### Scenario: limit 参数截断结果
- **WHEN** 调用 `list_by_user(user_id, limit=10)`
- **THEN** 返回记录数不超过 10 条

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

