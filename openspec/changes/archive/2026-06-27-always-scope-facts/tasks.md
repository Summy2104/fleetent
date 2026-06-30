## 1. Schema Migration

- [x] 1.1 在 `agent_state_migrations.py` 新增 migration：`ALTER TABLE facts ADD COLUMN scope TEXT NOT NULL DEFAULT 'situational'`，并回填已知 always relations
- [x] 1.2 编写 migration 测试（integration）：验证 scope 列存在、默认值、回填结果

## 2. facts_store 层

- [x] 2.1 编写 `list_always_facts(user_id)` 的单元测试（红）
- [x] 2.2 实现 `list_always_facts(user_id)`：`WHERE scope='always' AND status='active'`，纯 SQL，不走向量
- [x] 2.3 编写 soft 淘汰逻辑的单元测试（红）：soft 池满时写入触发淘汰最旧条目，hard/未知 relation 不被淘汰
- [x] 2.4 在 `upsert_fact()` 写入路径实现 soft 淘汰：定义 `SOFT_RELATIONS` 白名单，soft 池 ≥ 15 时 retract 最旧，未知 relation 默认 hard
- [x] 2.5 在 `Fact` dataclass 和 `_row_to_fact()` 中加入 `scope` 字段

## 3. facts_pipeline 提取

- [x] 3.1 编写提取 scope 判断的单元测试（红）：行为指令 → `always`，事实性偏好 → `situational`
- [x] 3.2 更新提取 prompt，新增 scope 输出字段说明和示例
- [x] 3.3 更新 `ExtractedFact` dataclass 加入 `scope` 字段（默认 `'situational'`）
- [x] 3.4 更新 pipeline 写库调用，传入 `scope`

## 4. long_term_ctx 注入

- [x] 4.1 编写 `build_context` always facts 注入的单元测试（红）：always facts 无条件出现在 directives section；无 always facts 时不出现空 section
- [x] 4.2 在 `build_context()` 中新增 `list_always_facts()` 调用（同步，在并发检索之前）
- [x] 4.3 新增 `[Behavioral directives — 始终生效的行为规则]` section 渲染，置于 `[Long-term memory]` 之前
- [x] 4.4 always facts sources 计入 `BuiltContext.sources`（`source_type="memory"`）

## 5. 集成验证

- [x] 5.1 编写 integration 测试：提取行为指令 → 写库 scope='always' → `build_context` 无条件注入，验证端到端
- [x] 5.2 `make test-pr` 全绿
