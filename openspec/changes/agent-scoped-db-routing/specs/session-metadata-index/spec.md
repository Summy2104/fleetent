## MODIFIED Requirements

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
