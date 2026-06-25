## ADDED Requirements

### Requirement: facts 表 schema
系统 SHALL 在 per-agent agent_state.db 中创建 `facts` 表，以三元组（subject, relation, object）为存储单元。

字段定义：
- `fact_id` TEXT PRIMARY KEY（UUIDv4）
- `user_id` TEXT NOT NULL
- `subject` TEXT NOT NULL（通常为用户自身，如 "user"；也可为其他实体）
- `relation` TEXT NOT NULL（归并后的规范化 relation 名）
- `object` TEXT NOT NULL（关系的值）
- `cardinality` TEXT NOT NULL CHECK IN ('single', 'multi')
- `status` TEXT NOT NULL CHECK IN ('active', 'superseded', 'archived', 'retracted')，默认 'active'
- `access_count` INTEGER NOT NULL DEFAULT 0
- `first_accessed_at` TEXT（ISO-8601 UTC，首次被检索命中时写入）
- `last_accessed_at` TEXT（ISO-8601 UTC，每次检索命中后更新）
- `expires_at` TEXT（ISO-8601 UTC；NULL = 长期记忆；非 NULL = 短期记忆）
- `valid_until` TEXT（ISO-8601 UTC；LLM 从对话提取的显式时间边界；NULL 表示无）
- `created_at` TEXT NOT NULL（ISO-8601 UTC）
- `updated_at` TEXT NOT NULL（ISO-8601 UTC）
- `source_turn` TEXT（来源对话 turn id，审计用）

索引：`(user_id, subject, relation, status)` 复合索引，支持 cardinality=single 时的快速覆盖查询。

#### Scenario: 新建 facts 表
- **WHEN** agent_state.db 执行嵌入式迁移（forward-only Y 模式）
- **THEN** facts 表以上述 schema 创建，PRAGMA user_version 递增到对应版本号

#### Scenario: fact_id 唯一性
- **WHEN** 同时插入两条 fact_id 相同的记录
- **THEN** 数据库抛出唯一约束违反错误，第二条插入回滚

---

### Requirement: fact_edges 表 schema
系统 SHALL 在 agent_state.db 中创建 `fact_edges` 表，记录事实间的 supersedes 链。

字段：
- `edge_id` TEXT PRIMARY KEY（UUIDv4）
- `from_fact_id` TEXT NOT NULL REFERENCES facts(fact_id)（新事实）
- `to_fact_id` TEXT NOT NULL REFERENCES facts(fact_id)（被取代的旧事实）
- `edge_type` TEXT NOT NULL DEFAULT 'supersedes'
- `created_at` TEXT NOT NULL

#### Scenario: supersedes edge 记录
- **WHEN** 新事实因 Contradict 裁决将旧事实标记为 superseded
- **THEN** fact_edges 中插入一行，from_fact_id = 新事实 id，to_fact_id = 旧事实 id，edge_type = 'supersedes'

#### Scenario: archived 事实无 supersedes edge
- **WHEN** 事实因生命周期到期被 archived（非 Contradict 替换）
- **THEN** 不插入 fact_edges 行（仅状态字段变更）

---

### Requirement: relation_clusters 词表 schema
系统 SHALL 在 agent_state.db 中创建 `relation_clusters` 表，维护规范化 relation 词汇表。

字段：
- `relation` TEXT PRIMARY KEY（规范化关系名，英文 snake_case）
- `cardinality` TEXT NOT NULL CHECK IN ('single', 'multi')
- `embedding` BLOB（relation 名称的向量，供归并时余弦计算；可为 NULL 直至首次计算）
- `created_at` TEXT NOT NULL

预置词条（系统初始化时写入）：
```
is_role          single
works_at         single
located_in       single
prefers_language single
speaks_language  multi
has_skill        multi
works_on_project multi
prefers_tool     multi
interested_in    multi
```

#### Scenario: 预置词条存在
- **WHEN** agent_state.db 完成迁移后首次调用 resolve_relation
- **THEN** relation_clusters 中已包含全部预置词条

#### Scenario: 新词条自动创建
- **WHEN** LLM 提取的 relation 与所有现有词条的余弦相似度均 < 0.90
- **THEN** 在 relation_clusters 中插入新词条，cardinality 由 LLM 同步判定

#### Scenario: 现有词条归并
- **WHEN** LLM 提取的 relation 与某现有词条余弦相似度 >= 0.90
- **THEN** 使用该现有词条（不插入新行），采用该词条的 cardinality
