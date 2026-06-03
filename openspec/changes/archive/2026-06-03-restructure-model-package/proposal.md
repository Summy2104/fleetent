## Why

蓝图迁移序列**第四包**（sandbox✅ → session → skills → **model** → tools → runtime）：把平铺的 `model_router.py`、`provider_health.py` 收进 `model/` 能力包。model_router 是全库 LLM 调用的咽喉（`get_client_and_config` 是测试 mock 的核心 patch 目标），文件少但调用方和 patch 面广，放在 tools/runtime 之前演练「高 patch 面」迁移。

## What Changes

- **迁移 2 文件**到 `src/fleetent/model/`，去冗余前缀（`git mv` 保留 blame）：
  `model_router.py`→`router.py`、`provider_health.py`→`provider_health.py`。
- **建 `model/__init__.py`** re-export 公共 API（`get_client_and_config`、`get_async_client_and_config`、`RouteConfig`、`RouteOverride`、`ROUTES`、`get_health_cache`、`ProviderHealthCache`、`ProviderState` 等）。
- **旧扁平路径留 re-export shim**（`model_router.py`、`provider_health.py`，不承载逻辑）。
- **改 src 直接调用方**：`agent_loop.py`、`server.py`、`context_mgr.py`、`intelligence/memory/extraction.py`、`observability/startup_diagnostics.py`。
- **迁移直接相关测试的 import 与 monkeypatch 目标**（`ROUTES_PATH`、`AsyncOpenAI`/`OpenAI` 构造、`ROUTES` 表等模块属性 patch 必须指向 `fleetent.model.router`；patch 调用方命名空间——如 `fleetent.agent_loop.get_async_client_and_config`——的测试不受影响）。
- 行为不变、无 schema 变更。

## Capabilities

### Modified Capabilities
- `package-architecture`: 记录 model 域**已完成包化**——`model/` 成包、公共 API 收口、旧路径仅 shim、契约/行为不变。

## Impact

- **代码**：新增 `src/fleetent/model/`（2 模块 + `__init__.py`）；旧 2 文件变 shim；5 处 src 调用方改 import。
- **测试**：`test_model_router.py` 大量 patch `model_router.ROUTES_PATH` / `AsyncOpenAI` 等模块属性——全部随迁到新模块；全库以 `get_client_and_config` 为 mock 锚点的测试多 patch 在**调用方**命名空间，不受影响（逐个 grep 确认）。
- **不受影响**：路由解析/fallback 链/参数合并逻辑、routes.yaml 格式、`ROUTES_PATH` 默认值（运行时 CWD 相对路径，不依赖 `__file__`）、provider 熔断缓存语义。
- **依赖**：蓝图 + 前序范式；建议在 skills 之后执行（无硬依赖，纯序列约定）。
- **分支**：基于并 PR 合回 `main`。
