## MODIFIED Requirements

### Requirement: Fast default feedback
PR 门禁 SHALL 优先运行快速且稳定的测试层，避免 e2e 或 evaluation 影响日常开发反馈。

#### Scenario: PR gate excludes evaluation tests
- **WHEN** Bitbucket PR pipeline 运行
- **THEN** pipeline 不默认运行 `tests/evaluation`
- **AND** 不调用真实 LLM 或真实 embedding evaluation

#### Scenario: Evaluation remains manually runnable
- **WHEN** 开发者运行 `uv run pytest tests/evaluation`
- **THEN** deterministic memory、knowledge-base、long-term context 和 reflection report evaluation 可以被手动执行
- **AND** 真实模型或真实 provider evaluation 只有在显式设置对应 `FLEETENT_EVAL_*` 环境变量时运行
