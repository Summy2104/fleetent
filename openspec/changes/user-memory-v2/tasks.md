## 1. Schema 与嵌入式迁移

- [x] 1.1 在 `src/fleetent/memory/facts_migrations.py` 定义 `FACTS_MIGRATIONS = [(ver, sql)]`，包含 facts / fact_edges / relation_clusters 三张表的建表 SQL 及复合索引
- [x] 1.2 在 `src/fleetent/memory/facts_migrations.py` 定义预置词条 seed SQL（9 条 relation_clusters 初始数据）
- [x] 1.3 将 FACTS_MIGRATIONS 合并进 `agent_state_migrations.py`（AGENT_STATE_MIGRATIONS 列表末尾追加），版本号递增
- [x] 1.4 写测试（integration）：agent_state.db 迁移后三张表存在、预置词条存在、PRAGMA user_version 正确

## 2. 数据模型

- [x] 2.1 在 `src/fleetent/memory/facts_models.py` 定义 `Fact`、`FactEdge`、`RelationCluster`、`RawFact`、`ResolvedFact`、`ClassifiedFact`、`SearchResult` dataclass（含完整类型注解）
- [x] 2.2 在 `facts_models.py` 定义 `FactStatus = Literal['active', 'superseded', 'archived', 'retracted']`、`Cardinality = Literal['single', 'multi']`、`ClassifyVerdict = Literal['Equivalent', 'Contradict', 'NewSubsumed', 'Subsumes', 'Orthogonal']`
- [x] 2.3 写测试（unit）：dataclass 字段完整性、Literal 类型取值覆盖

## 3. facts_store — SQL 访问层

- [x] 3.1 写测试（integration）：`insert_fact` 插入成功、fact_id 唯一约束报错
- [x] 3.2 实现 `facts_store.py`：`insert_fact`、`update_fact_status`、`get_fact`、`facts_by_ids`、`active_facts_for_relation`
- [x] 3.3 写测试（integration）：`insert_fact_edge` / `get_supersedes_chain`
- [x] 3.4 实现 `insert_fact_edge`、`get_supersedes_chain`
- [x] 3.5 写测试（integration）：`get_relation_cluster`（精确匹配 + 不存在返回 None）、`insert_relation_cluster`、`list_relation_clusters`
- [x] 3.6 实现 `get_relation_cluster`、`insert_relation_cluster`、`list_relation_clusters`
- [x] 3.7 写测试（integration）：`update_fact_access`（access_count +1、last_accessed_at 更新、first_accessed_at 仅首次写入）
- [x] 3.8 实现 `update_fact_access`

## 4. facts_store — DB 注入

- [x] 4.1 写测试（unit）：调用 store 函数前未 set_facts_db 时抛 RuntimeError
- [x] 4.2 实现 `set_facts_db(db, vector_backend)`、`_facts_database()`、`_facts_vector_backend()` 注入守卫（仿 agent_memory.py 模式）

## 5. resolve_relation — relation 归并

- [x] 5.1 写测试（unit）：`resolve_relation` 在词表为空时直接插入新词条
- [x] 5.2 写测试（unit）：`resolve_relation` 余弦 >= 0.90 归并到现有词条（mock embed_text）
- [x] 5.3 写测试（unit）：`resolve_relation` 余弦 < 0.90 创建新词条（mock embed_text）
- [x] 5.4 实现 `src/fleetent/memory/facts_pipeline.py`：`resolve_relation(raw_fact, db) -> ResolvedFact`

## 6. classify_relation — LLM 裁决

- [x] 6.1 写测试（unit）：`classify_relation` 返回 ClassifyVerdict 枚举值（mock LLM call）
- [x] 6.2 写测试（unit）：`classify_relation` 当无 active 旧事实时直接返回 Orthogonal
- [x] 6.3 实现 `classify_relation(resolved_fact, existing_facts, llm_client) -> ClassifiedFact`（LLM prompt 含 subject/relation/old_object/new_object）

## 7. commit_facts — 事务提交

- [x] 7.1 写测试（integration）：single cardinality Contradict → 旧 fact superseded，新 fact active，fact_edge 记录
- [x] 7.2 写测试（integration）：multi cardinality Orthogonal → 两条 fact 均 active
- [x] 7.3 写测试（integration）：Equivalent 裁决 → 不插入新行，总 active fact 数不变
- [x] 7.4 写测试（integration）：事务回滚（模拟提交中途异常 → 所有变更回滚）
- [x] 7.5 实现 `commit_facts(classified_facts, db) -> list[Fact]`（SQLite 事务 + 状态机逻辑）
- [x] 7.6 实现事务提交后异步向量 upsert（新 active fact）/ delete（旧 superseded fact）

## 8. extract_facts — LLM 提取流水线

- [x] 8.1 写测试（unit）：`extract_facts` 正常提取单条（mock LLM），返回含 valid_until 的 RawFact
- [x] 8.2 写测试（unit）：`extract_facts` 对话无新事实时返回空列表
- [x] 8.3 写测试（unit）：LLM 输出格式错误时跳过该条并 warning 日志
- [x] 8.4 实现 `extract_facts(turn_content, llm_client) -> list[RawFact]`（含 prompt 构造 + JSON 解析 + 异常处理）

## 9. 写入流水线编排

- [x] 9.1 写测试（unit）：`run_pipeline` end-to-end 以 mock LLM / vector → facts 写入 DB（集成所有步骤）
- [x] 9.2 实现 `run_pipeline(user_id, turn_content, db, vector_backend, llm_client)`（串联 extract → resolve → classify → commit）

## 10. search_facts — 检索接口

- [x] 10.1 写测试（unit）：`search_facts` 返回 SearchResult 列表，status != 'active' 的被过滤
- [x] 10.2 写测试（unit）：max_score < 0.5 → access 字段不更新（mock 向量 score）
- [x] 10.3 写测试（unit）：max_score >= 0.5 → access 字段异步更新（mock 并验证调用）
- [x] 10.4 写测试（unit）：max_score == 0.5 → 视为高相关，触发 access 更新
- [x] 10.5 实现 `src/fleetent/memory/facts_search.py`：`search_facts(user_id, query, limit, db, vector_backend)`
- [x] 10.6 实现 access 异步更新（含升级检查：access_count >= 10 AND first_accessed_at <= now-14d → expires_at = NULL）

## 11. 生命周期 — 消亡 + pin + retract

- [x] 11.1 写测试（integration）：`archive_expired_facts` archive expires_at 到期的 short-term fact
- [x] 11.2 写测试（integration）：`archive_expired_facts` archive last_accessed_at > 30 天的 short-term fact（expires_at 未到）
- [x] 11.3 写测试（integration）：`archive_expired_facts` 不影响 expires_at IS NULL 的 long-term fact
- [x] 11.4 实现 `src/fleetent/memory/facts_lifecycle.py`：`archive_expired_facts(db, vector_backend)`
- [x] 11.5 写测试（unit）：`pin_fact` 将 expires_at 设为 NULL；对非 active fact 抛 ValueError
- [x] 11.6 实现 `pin_fact(fact_id, db)`
- [x] 11.7 写测试（unit）：`retract_fact` 设 status = retracted，删向量；`retract_by_relation` 批量 retract
- [x] 11.8 实现 `retract_fact(fact_id, db, vector_backend)`、`retract_by_relation(user_id, subject, relation, db, vector_backend)`

## 12. 后台 job 注册

- [x] 12.1 写测试（integration）：agent boot 后 `archive_expired_facts` job 已注册（检查 job registry）
- [x] 12.2 在 `agent_app.py` boot 流程中将 `archive_expired_facts` 注册为 1 小时间隔定时任务（舱壁化：job 失败只记 error 日志）

## 13. 公开接口迁移

- [x] 13.1 写测试（unit）：调用旧 `memory.search()` 触发 DeprecationWarning，返回空列表
- [x] 13.2 在 `src/fleetent/memory/__init__.py` 暴露 `search_facts`、`run_pipeline`、`pin_fact`、`retract_fact`、`set_facts_db`
- [x] 13.3 将旧 `search()`、`extract_and_update()` 标记 deprecated（抛 DeprecationWarning，不实现逻辑）
- [x] 13.4 更新调用旧接口的 runtime 代码（`runtime/loop.py`、`long_term_ctx`、`reflection`），切换到新 `run_pipeline`/`search_facts`；reflection conflict 检测重写为 facts 三元组语义

## 14. 模块边界护栏

- [x] 14.1 运行 `uv run pytest tests/unit/test_module_dependency_guardrails.py -x -q`，确认新 memory/ 代码无 platform.* 反向 import（13 passed）
- [x] 14.2 运行 `make test-pr`，确认无新增失败（3693 passed；2 个预先存在失败 test_admin_entrypoint_cleanup / test_intelligence_shim_removal，main 基线同样失败，非本 change）
- [x] 14.3 运行 `uv run pytest tests/integration -q`，对照 main 基线无新增失败（2103 passed；5 个预先存在失败 test_deployment_docs / test_scheduled_task_session_binding，main 基线同样失败）
