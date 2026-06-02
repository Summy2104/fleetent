## ADDED Requirements

### Requirement: Memory extraction evaluation fixtures
系统 SHALL 提供 memory extraction evaluation fixtures，用于通过 mock actions 驱动提取流程，并验证最终 memory 状态。

#### Scenario: Fixture schema is explicit
- **WHEN** evaluation runner 加载 fixture
- **THEN** fixture 包含 name、initial_memories、conversation、mock_actions、expected_memories 和 forbidden_memories

#### Scenario: Invalid fixture is rejected
- **WHEN** fixture 缺失必需字段或包含非法 action 类型
- **THEN** evaluation runner 报告 fixture validation failure

### Requirement: Deterministic memory extraction evaluation
系统 SHALL 默认通过 mock LLM 运行 memory extraction evaluation，保证评估稳定且不依赖外部模型。

#### Scenario: Mock actions drive extraction
- **WHEN** evaluation fixture 提供 mock_actions
- **THEN** evaluation runner 使用 mock_actions 驱动 `extract_and_update()`
- **AND** 不调用真实 LLM 服务

#### Scenario: Expected memory state is validated
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 expected_memories 对应的 memory 状态存在

#### Scenario: Forbidden memory state is rejected
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 forbidden_memories 对应的 memory 状态不存在

#### Scenario: Evaluation isolates storage and vector dependencies
- **WHEN** evaluation case 运行
- **THEN** SQLite 使用 tmp path 隔离
- **AND** vector_store 被 mock 或使用测试替身
- **AND** 不触碰 `data/`

### Requirement: Memory extraction scenario coverage
系统 SHALL 覆盖第一批 memory extraction 质量基线场景。

#### Scenario: Identity create is covered
- **WHEN** 用户首次提供稳定身份事实
- **THEN** evaluation 验证最终存在对应的 identity memory

#### Scenario: Identity update is covered
- **WHEN** 用户修正已有身份事实
- **THEN** evaluation 验证最终 identity memory 已更新为新事实

#### Scenario: Context update is covered
- **WHEN** 用户更新当前项目或临时状态
- **THEN** evaluation 验证最终 context memory 已更新为新状态

#### Scenario: Preference create is covered
- **WHEN** 用户明确表达长期偏好
- **THEN** evaluation 验证最终存在对应的 preferences memory

#### Scenario: One-off preference request is covered
- **WHEN** 用户只提出一次性格式或输出要求
- **THEN** evaluation 验证最终不存在对应的一次性 preferences memory

#### Scenario: Explicit forget is covered
- **WHEN** 用户明确要求忘记某条记忆
- **THEN** evaluation 验证最终不存在被遗忘的 memory

#### Scenario: Noisy conversation ignore is covered
- **WHEN** 对话没有可记忆事实或内容噪声较多
- **THEN** evaluation 验证最终不新增 memory

### Requirement: Optional real LLM memory extraction evaluation
系统 SHALL 提供显式启用的真实 LLM memory extraction evaluation 入口，且默认跳过。

#### Scenario: Real LLM evaluation is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_LLM=1`
- **THEN** 真实 LLM evaluation case 被 skip

#### Scenario: Real LLM evaluation requires explicit opt-in
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LLM=1`
- **THEN** runner 可以使用真实 `memory_extraction` 路由运行 fixture

#### Scenario: Real LLM evaluation skips when provider credentials are missing
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LLM=1` 但缺少真实 provider API key
- **THEN** 真实 LLM evaluation case 被 skip

#### Scenario: Real LLM evaluation is not a PR gate
- **WHEN** Bitbucket PR/main pipeline 运行
- **THEN** pipeline 不默认运行真实 LLM evaluation
