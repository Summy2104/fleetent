## ADDED Requirements

### Requirement: 共享记忆经 per-tenant 库 + WAL 多写

shared memory（`shared_memory_items`）的 schema SHALL 经 per-tenant `shared_memory.db`（`tenant_scope` + 嵌入式 Y）建立；`memory/shared.py` 连接 SHALL 走 `tenant_scope`、不自连接全局库。多 agent 并发写 SHALL 由连接层 WAL + `busy_timeout`（见 `database-runtime` SQLite 并发模式）原生串行化，MUST NOT 引入应用层写队列/锁。

#### Scenario: 共享记忆 schema 经 tenant_scope + Y

- **WHEN** 初始化某主体的共享记忆存储
- **THEN** `shared_memory_items` 经 `tenant_scope` 取 `shared_memory.db` 后由嵌入式 Y 建立

#### Scenario: 多 agent 写靠 WAL 串行

- **WHEN** 同主体两个 agent 近乎同时写共享记忆
- **THEN** 经 WAL + busy_timeout 串行成功，无需应用层锁/队列，platform 只读投影可并发读（WAL）
