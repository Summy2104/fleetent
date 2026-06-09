# session-metadata-index Delta Spec

## MODIFIED Requirements

### Requirement: session 元数据存储

系统 SHALL 在**统一 `db.py` runtime 所指向的数据库**（由 `DATABASE_URL` 解析，标准 agent 即 per-agent
库）的 `sessions` 表中为每个 session 维护轻量元数据，至少包含 `session_id`、`user_id`、`created_at`、
`updated_at`（最后活跃时间）、`message_count`、`agent_name`。元数据 MUST 存于数据库表，与 session 的
消息 JSON 文件物理分离，MUST NOT 增加消息文件本身的体积。`session/index.py` SHALL 经由
`fleetent.db.create_database` + 幂等 `ensure_schema(db)` 访问该表，SHALL NOT 使用裸 `sqlite3.connect`，
SHALL NOT 写入独立的 `users.db` 文件。

#### Scenario: 首次记录创建元数据

- **WHEN** 某 session 首次被记录活跃
- **THEN** `sessions` 表新增一行，`created_at` 与 `updated_at` 均为当前时间，`message_count` 为当前消息数

#### Scenario: 元数据存于统一库且与消息文件分离

- **WHEN** 写入 session 元数据
- **THEN** 元数据写入 `DATABASE_URL` 指向的统一库的 `sessions` 表
- **AND** 不创建或写入 `users.db`
- **AND** session 消息 JSON 文件内容不因此增加元数据字段

#### Scenario: 经统一 runtime 访问

- **WHEN** `session/index.py` 读写元数据
- **THEN** 经由 `fleetent.db` 的 `create_database` / `SQLiteDatabase`，模块内不出现 `sqlite3.connect`
