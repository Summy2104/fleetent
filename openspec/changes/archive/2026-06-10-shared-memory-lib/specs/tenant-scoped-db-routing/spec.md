## ADDED Requirements

### Requirement: tenant_scope 含共享记忆句柄

`tenant_scope(tenant)` SHALL 除 KB 句柄外，再返回该主体的**共享记忆**句柄——`shared_memory.db` 关系连接 + `shared:` 家族向量后端。SQLite 后端 SHALL 映射到 `<tenant>/shared_memory.db` 与 `<tenant>/shared_memory_vectors.db`。共享记忆与 KB 同属 per-tenant 作用域，但 agent 对共享记忆取**读写**连接（KB 为只读）。

#### Scenario: tenant_scope 返回共享记忆句柄

- **WHEN** 解析 `tenant_scope(T)`
- **THEN** 可取得 `<T>/shared_memory.db` 关系连接与 `shared:` 向量后端

#### Scenario: agent 对共享记忆可写

- **WHEN** agent 经 `tenant_scope` 取共享记忆连接
- **THEN** 该连接为读写（共享记忆是多 agent 写的真相源），而 KB 连接为只读
