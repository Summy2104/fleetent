## MODIFIED Requirements

### Requirement: Layered test suite organization
系统 SHALL 按测试成本和依赖范围组织测试目录。

#### Scenario: Root test files are migrated
- **WHEN** 历史测试迁移完成
- **THEN** `tests/` 根目录不再包含 `test_*.py` 文件
- **AND** 历史测试按 unit、integration、e2e 或 evaluation 放入对应目录

#### Scenario: Test directories remain authoritative
- **WHEN** 团队新增或移动测试
- **THEN** 测试 SHALL 放入 `tests/unit/`、`tests/integration/`、`tests/e2e/` 或 `tests/evaluation/`
- **AND** 不得继续向 `tests/` 根目录新增测试文件

### Requirement: Fast default feedback
PR 门禁 SHALL 优先运行快速且稳定的测试层，避免 e2e 或 evaluation 影响日常开发反馈。

#### Scenario: PR gate covers migrated unit and integration tests
- **WHEN** Bitbucket PR pipeline 运行
- **THEN** pipeline 运行 `uv run pytest tests/unit`
- **AND** pipeline 运行 `uv run pytest tests/integration`
- **AND** 不默认运行 e2e 或 evaluation tests

#### Scenario: Full test command collects only explicit layers
- **WHEN** 调用 `uv run pytest`
- **THEN** pytest 从 `tests/unit`、`tests/integration`、`tests/e2e` 和 `tests/evaluation` 收集测试
- **AND** 不依赖 `tests/` 根目录平铺测试收集

### Requirement: Agent guidance matches test layers
项目级 agent 指南 SHALL 说明测试目录分层，保证 AI agent 和团队成员按同一规范写测试。

#### Scenario: Root compatibility guidance is removed
- **WHEN** 读者查看 `AGENTS.md` 或 `CLAUDE.md`
- **THEN** 文档不再描述 `tests/` 根目录作为新增或保留测试位置
- **AND** 文档说明历史测试已经迁移到分层目录
