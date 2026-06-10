## ADDED Requirements

### Requirement: 租户作用域路由入口

系统 SHALL 提供单一的"租户作用域"路由入口，调用方只表达"在某个 tenant 作用域里访问"，由路由解析出该作用域的物理后端句柄（关系库连接 + 向量后端）。调用方 MUST NOT 自行拼接物理路径或直接打开库文件。

#### Scenario: 按主体解析后端

- **WHEN** 调用方请求 tenant `default` 作用域的 KB 关系库与向量后端
- **THEN** 路由返回该主体对应的 `SQLiteDatabase` 连接与向量后端句柄

#### Scenario: KB 关系库与向量库同源于一个作用域

- **WHEN** 同一 tenant 作用域同时取关系库与向量后端
- **THEN** 二者由同一次 `scope(tenant)` 解析得到，绑定到同一主体

### Requirement: 可换后端抽象

路由后端 SHALL 可插拔：当下 SQLite 后端把 tenant 作用域映射到 `<tenant>/` 目录下的物理文件；后端实现 MUST 可替换为其它实现（如将来 PostgreSQL per-tenant database 或 RLS），而调用点不变。

#### Scenario: SQLite 后端映射到主体目录文件

- **WHEN** 在 SQLite 后端下解析 tenant `T` 的 KB 关系库
- **THEN** 连接指向 `T` 主体目录下的 KB 库文件，物理上不触及其它主体的库

#### Scenario: 切换后端不改调用点

- **WHEN** 后端实现被替换
- **THEN** 调用方仍只通过 `scope(tenant)` 取后端，调用代码无需改动

### Requirement: KB 内容存储连接来自路由

KB **内容存储**（`KnowledgeStore` 及 `knowledge_base/operations.py`，服务 knowledge_bases/documents/chunks 等内容表）SHALL 从路由获取连接；这部分 MUST NOT 通过 `create_database(settings.database_url)` 等方式自连接全局库。系统 SHALL 提供护栏测试断言此约束。`knowledge_base/bindings.py`（绑定表 `knowledge_base_agent_bindings`）**不在本切片范围**——其连接来源与表归属由兄弟切片 3a-binding 处理，本切片不改动。

#### Scenario: KnowledgeStore 经构造注入路由连接

- **WHEN** 构造 `KnowledgeStore`
- **THEN** 其 `database` 由路由提供，而非模块内部自连接

#### Scenario: 护栏捕获内容存储自连接旁路

- **WHEN** KB 内容存储（KnowledgeStore / operations.py）出现 `create_database(...settings...)` 之类的自连接路径
- **THEN** 护栏测试失败并指出该旁路

#### Scenario: 绑定模块不在本切片

- **WHEN** 检查 `knowledge_base/bindings.py` 的连接来源
- **THEN** 本切片不要求其改动（归 3a-binding），护栏范围不含 bindings.py

### Requirement: 单主体作用域先行

3a SHALL 仅支持单主体 `default` 作用域：`scope("default")` 返回单一后端；多主体 per-tenant 目录 fan-out 不在本切片（留后续）。抽象 MUST 已就位，使后续启用多主体时调用点不变。

#### Scenario: default 作用域返回单一后端

- **WHEN** 解析 `scope("default")`
- **THEN** 返回单一主体的后端句柄，不做多主体目录展开

### Requirement: tenant_id 列保留为可换后端接缝

KB 表 SHALL 保留 `tenant_id`/`kb_id` 列。SQLite 文件路由忽略 `tenant_id`（文件本身即主体边界）；将来 RLS 后端 MUST 能按 `tenant_id` 列做行级强制。该列不得因物理分库而删除。

#### Scenario: 物理分库后列仍在

- **WHEN** KB 关系库按主体路由到独立文件
- **THEN** 表结构仍含 `tenant_id`/`kb_id` 列（供可换后端 / RLS 使用）
