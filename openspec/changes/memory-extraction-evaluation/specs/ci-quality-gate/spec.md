## MODIFIED Requirements

### Requirement: Fast default feedback
PR 门禁 SHALL 优先运行快速且稳定的测试层，避免 e2e 或 evaluation 影响日常开发反馈。

#### Scenario: PR gate excludes memory extraction evaluation
- **WHEN** Bitbucket PR pipeline 运行
- **THEN** pipeline 不默认运行 `tests/evaluation`
- **AND** 不调用真实 LLM evaluation

#### Scenario: Evaluation remains manually runnable
- **WHEN** 开发者运行 `uv run pytest tests/evaluation`
- **THEN** memory extraction mock evaluation 可以被手动执行
- **AND** 真实 LLM evaluation 只有在显式设置 `FLEETENT_EVAL_REAL_LLM=1` 时运行
