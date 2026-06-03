## ADDED Requirements

### Requirement: sandbox 域已迁入 integrations/sandbox

sandbox 能力域 SHALL 组织为 `integrations/sandbox/` package:公共 API 收口于其 `__init__.py`;原 `src/fleetent/sandbox_*.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim;迁移 SHALL 不改变运行时行为、`run_code` 工具契约或 schema。

#### Scenario: sandbox 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/integrations/sandbox/`
- **THEN** 它含 `__init__.py` + `client/config/manager/enablement/cleanup/secrets/output_truncation.py`,且 `__init__.py` 导出 `SandboxClient`、`Mode`、`cleanup_orphans`、`SandboxManager` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看任一旧路径(如 `src/fleetent/sandbox_client.py`)
- **THEN** 它只从 `fleetent.integrations.sandbox.*` re-export,不含函数/类定义

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试(`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`)通过,且无 schema 变更
