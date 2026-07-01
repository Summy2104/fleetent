## ADDED Requirements

### Requirement: search_facts — 向量检索 + 存活过滤
系统 SHALL 提供 `search_facts(user_id, query, limit)` 函数，返回与 query 语义相关的 active facts。

检索流程：
1. 调用 `vector_store.embed_text(query)` 获得查询向量
2. 在 VectorBackend 中以 namespace = `umem:{user_id}` 检索，返回最多 `limit * 2` 条候选（冗余候选用于存活过滤后仍有足够结果）
3. 按 fact_id 批量查询 facts 表，过滤 status = 'active'
4. 保留向量排序，截断到 `limit` 条
5. 返回 `SearchResult` 列表：`{fact: Fact, score: float}`

`limit` 默认值 10。

#### Scenario: 正常检索返回 active facts
- **WHEN** search_facts(user_id="u1", query="我的编程语言偏好", limit=5)
- **THEN** 返回最多 5 条 status='active' 的 facts，按向量相似度降序排列

#### Scenario: 过滤非 active facts
- **WHEN** 向量检索候选中包含 status='superseded' 和 status='archived' 的 fact
- **THEN** 这些 fact 不出现在返回结果中

#### Scenario: 无相关结果
- **WHEN** 用户记忆库为空或 query 无相关 fact
- **THEN** 返回空列表

---

### Requirement: max_score 门控 — 低相关对话不更新 access
系统 SHALL 在 search_facts 完成后，检查所有候选的最高 score。

若 max_score < 0.5（含无结果时）：
- 返回检索结果（供 LLM 判断使用）
- **不**更新任何 fact 的 `last_accessed_at`、`access_count`、`first_accessed_at`

若 max_score >= 0.5：
- 对所有出现在返回结果中的 facts 异步更新 access 字段（见下一条 Requirement）

#### Scenario: 高相关检索触发 access 更新
- **WHEN** search_facts 返回最高 score = 0.82 的结果
- **THEN** 结果中每条 fact 的 access_count +1，last_accessed_at 更新为 now；首次命中时写入 first_accessed_at

#### Scenario: 低相关检索不更新 access
- **WHEN** search_facts 返回最高 score = 0.41（或返回空列表）
- **THEN** 所有 fact 的 access_count、last_accessed_at、first_accessed_at 均不变

#### Scenario: 恰好等于 0.5 视为高相关
- **WHEN** max_score = 0.5
- **THEN** 触发 access 更新（门控为严格小于 0.5 才跳过）

---

### Requirement: access 字段异步更新 + 升级检查
系统 SHALL 在 max_score >= 0.5 时，对命中 facts 执行以下更新（异步，不阻塞检索返回）：

- `access_count = access_count + 1`
- `last_accessed_at = now`
- 若 `first_accessed_at IS NULL`：`first_accessed_at = now`
- `updated_at = now`

更新后触发升级检查（`user-memory-lifecycle` Requirement: 自动升级为长期记忆）。

向量 upsert 无需在此执行（fact object 未变化，向量无需更新）。

#### Scenario: first_accessed_at 仅写一次
- **WHEN** fact 第 2 次被检索命中（first_accessed_at 已有值）
- **THEN** first_accessed_at 不变；access_count = 2；last_accessed_at 更新为本次时间

#### Scenario: 异步更新失败不影响检索返回
- **WHEN** access 异步更新因数据库锁超时失败
- **THEN** search_facts 已返回结果给调用方；warning 日志记录更新失败；下次命中时重试

---

### Requirement: search 公开接口
系统 SHALL 在 `fleetent.memory` 公开接口中暴露 `search_facts`，替代旧 `search` 函数。

旧 `search()` 函数标记为 deprecated（保留签名，抛出 DeprecationWarning）。

返回类型从 `list[MemoryItem]` 改为 `list[SearchResult]`（含 fact + score）。

#### Scenario: 旧调用方收到 DeprecationWarning
- **WHEN** 调用旧 `memory.search(user_id, query)`
- **THEN** 抛出 DeprecationWarning；返回空列表（不转换格式，避免误导）

#### Scenario: 新接口正常调用
- **WHEN** 调用 `memory.search_facts(user_id="u1", query="my skills")`
- **THEN** 返回 `list[SearchResult]`，每项含 fact 和 score
