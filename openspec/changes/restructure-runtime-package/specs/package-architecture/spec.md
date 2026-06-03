## ADDED Requirements

### Requirement: runtime 域已迁入 runtime/

runtime 能力域 SHALL 组织为 `runtime/` package（13 模块包内平铺，不预拆子包）：公共 API 收口于其 `__init__.py`；原 `agent_loop.py`、`context_mgr.py`、`agent_runtime.py` 及 10 个治理模块的平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim；迁移 SHALL 不改变 run/run_stream 契约、压缩语义、预算/取消/终止行为或工具注册副作用链。至此蓝图定义的 7 个能力包 SHALL 全部落地。

#### Scenario: runtime 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/runtime/`
- **THEN** 它含 `__init__.py` + `loop.py`、`context.py`、`snapshot.py` 等 13 个模块，且 `__init__.py` 导出 `run`、`run_stream`、`CancelToken` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看任一旧路径（如 `src/fleetent/agent_loop.py`）
- **THEN** 它只从 `fleetent.runtime.*` re-export，不含函数/类定义

#### Scenario: 测试 patch 目标已随迁
- **WHEN** 检索 `tests/**` 中对 agent_loop / context_mgr 模块属性的 patch/monkeypatch
- **THEN** patch 目标均为 `fleetent.runtime.loop` / `fleetent.runtime.context`（非旧 shim 路径）

#### Scenario: 注册副作用链存活
- **WHEN** `import fleetent.runtime.loop` 后调用 `get_schemas()`
- **THEN** 内置工具列表非空且与迁移前数量一致

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更
