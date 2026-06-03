## ADDED Requirements

### Requirement: session 域已迁入 session/

session 能力域 SHALL 组织为 `session/` package：公共 API 收口于其 `__init__.py`；原 `src/fleetent/session_mgr.py`、`session_index.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim；迁移 SHALL 不改变 session 持久化格式、原子写语义或运行时行为。

#### Scenario: session 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/session/`
- **THEN** 它含 `__init__.py` + `manager.py` + `index.py`，且 `__init__.py` 导出 `load`、`save`、`session_lock`、`SESSIONS_DIR` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看 `src/fleetent/session_mgr.py` 或 `session_index.py`
- **THEN** 它只从 `fleetent.session.*` re-export，不含函数/类定义

#### Scenario: 测试 patch 目标已随迁
- **WHEN** 检索 `tests/**` 中对 session 模块属性的 monkeypatch
- **THEN** patch 目标均为 `fleetent.session.manager`（非旧 shim 路径）

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更
