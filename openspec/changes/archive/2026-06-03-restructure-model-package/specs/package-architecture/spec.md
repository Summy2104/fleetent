## ADDED Requirements

### Requirement: model 域已迁入 model/

model 能力域 SHALL 组织为 `model/` package：公共 API 收口于其 `__init__.py`；原 `src/fleetent/model_router.py`、`provider_health.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim；迁移 SHALL 不改变路由解析、fallback 链、routes.yaml 契约或 provider 熔断语义。

#### Scenario: model 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/model/`
- **THEN** 它含 `__init__.py` + `router.py` + `provider_health.py`，且 `__init__.py` 导出 `get_client_and_config`、`RouteConfig`、`get_health_cache` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看 `src/fleetent/model_router.py` 或 `provider_health.py`
- **THEN** 它只从 `fleetent.model.*` re-export，不含函数/类定义

#### Scenario: 可变全局的 patch 目标已随迁
- **WHEN** 检索 `tests/**` 中对 `ROUTES_PATH`、`ROUTES` 等模块属性的 monkeypatch
- **THEN** patch 目标均为 `fleetent.model.router`（非旧 shim 路径）

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更
