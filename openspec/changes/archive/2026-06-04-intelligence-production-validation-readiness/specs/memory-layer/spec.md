## MODIFIED Requirements

### Requirement: Memory extraction actions

`extract_and_update()` SHALL 调用 memory_extraction 模型，并处理 `create`、`update`、`delete`
与 `ignore` action。

#### Scenario: Create action writes memory
- **WHEN** LLM 返回 action=`create`、合法 type 和非空 content
- **THEN** 系统写入一条 memory item
- **AND** 调用 `vector_store.upsert()` 同步索引

#### Scenario: Update action changes existing memory
- **WHEN** LLM 返回 action=`update`、合法 `target_id`、合法 type 和非空 content
- **THEN** 系统更新该 memory item 的 content 和 updated_at
- **AND** 调用 `vector_store.upsert(target_id, content, memory_namespace(user_id))`

#### Scenario: Context update refreshes TTL
- **WHEN** context memory 被 update
- **THEN** expires_at 被刷新为 updated_at 后 30 天

#### Scenario: Identity and preferences update do not expire
- **WHEN** identity 或 preferences memory 被 update
- **THEN** expires_at 为 NULL

#### Scenario: Delete action removes existing memory
- **WHEN** LLM 返回 action=`delete` 和合法 `target_id`
- **THEN** 系统删除该 memory item
- **AND** 调用 `vector_store.delete(target_id, memory_namespace(user_id))`

#### Scenario: Ignore action does not mutate memory
- **WHEN** LLM 返回 action=`ignore`
- **THEN** 系统不写入、不更新、不删除 memory item

#### Scenario: JSON array may be wrapped by real provider prose
- **WHEN** memory_extraction 返回 raw JSON array、fenced JSON array、或带说明文字的 fenced/inline JSON array
- **THEN** 系统解析其中第一段有效 JSON array 并按 action contract 处理

#### Scenario: Valid memory content is normalized before mutation
- **WHEN** LLM 返回合法 action 但 content 使用等价的一人称、裸 noun phrase 或 `Prefers ...` 表述
- **THEN** 系统在写入前按 memory type 归一化为 user-scoped content
- **AND** 不改变 target_id、memory type、delete action 或 unsupported action

#### Scenario: Invalid mutation output is ignored
- **WHEN** LLM 返回非法 JSON、未知 action、非法 type、空 content、缺失 target_id、不属于当前用户的 target_id、或无有效 JSON array 的文本
- **THEN** 系统跳过对应输出，不向 agent_runtime 抛出异常

### Requirement: Optional real LLM memory extraction evaluation

系统 SHALL 提供显式启用的真实 LLM memory extraction evaluation 入口，且默认跳过。

#### Scenario: Real LLM evaluation is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_LLM=1`
- **THEN** 真实 LLM evaluation case 被 skip

#### Scenario: Real LLM evaluation requires explicit opt-in
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LLM=1`
- **THEN** runner 可以使用真实 `memory_extraction` 路由运行 fixture

#### Scenario: Real LLM evaluation preserves operator credentials
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LLM=1` 且 operator 已提供真实 provider API key
- **THEN** evaluation runner 使用该真实 credential path 调用 `memory_extraction`
- **AND** 默认测试夹具不得把该 real-provider path 强制替换为 `test-key`

#### Scenario: Real LLM evaluation skips when provider credentials are missing
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LLM=1` 但缺少真实 provider API key
- **THEN** 真实 LLM evaluation case 被 skip
- **AND** skip reason 指明需要配置真实 provider credential

#### Scenario: Real LLM evaluation is not a PR gate
- **WHEN** Bitbucket PR/main pipeline 运行
- **THEN** pipeline 不默认运行真实 LLM evaluation
