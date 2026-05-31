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

#### Scenario: Invalid mutation output is ignored
- **WHEN** LLM 返回非法 JSON、未知 action、非法 type、空 content、缺失 target_id 或不属于当前用户的 target_id
- **THEN** 系统跳过对应输出，不向 agent_runtime 抛出异常

## ADDED Requirements

### Requirement: Existing memory snapshot for extraction
`extract_and_update()` SHALL 在调用 memory_extraction 模型时提供有限的现有 memory snapshot，
供模型判断 create、update、delete 或 ignore。

#### Scenario: Snapshot includes bounded memory by type
- **WHEN** `extract_and_update()` 构造 extraction 输入
- **THEN** identity snapshot 最多包含 20 条
- **AND** preferences snapshot 最多包含 30 条
- **AND** context snapshot 最多包含 20 条

#### Scenario: Snapshot excludes expired context
- **WHEN** 用户存在已过期 context memory
- **THEN** extraction snapshot 不包含该 memory

#### Scenario: Snapshot belongs to current user only
- **WHEN** 系统为 user A 执行 extraction
- **THEN** snapshot 不包含其他用户的 memory item

### Requirement: Memory conflict handling through update actions
系统 SHALL 通过 extraction action contract 处理明显冲突和一次性偏好请求，避免无界追加矛盾记忆。

#### Scenario: Identity conflict updates existing item
- **WHEN** 用户新对话修正了已有 identity 事实，且 LLM 返回 update action
- **THEN** 系统更新目标 identity memory
- **AND** 不追加一条矛盾 identity memory

#### Scenario: Context conflict updates existing item
- **WHEN** 用户新对话修正了已有 context 状态，且 LLM 返回 update action
- **THEN** 系统更新目标 context memory
- **AND** 刷新 context TTL

#### Scenario: One-off preference is ignored
- **WHEN** 用户只提出一次性格式或输出要求，且 LLM 返回 ignore action
- **THEN** 系统不创建 preferences memory
