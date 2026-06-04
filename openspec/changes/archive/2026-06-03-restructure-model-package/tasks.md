> 纯结构重构：用既有全量测试套件作为回归安全网，每步后保持绿。

## 1. 基线

- [x] 1.1 记录基线：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 全绿；`mypy src` 现有错误数

## 2. 移文件 + 建包

- [x] 2.1 `git mv` `model_router.py`→`model/router.py`、`provider_health.py`→`model/provider_health.py`
- [x] 2.2 建 `model/__init__.py`：re-export 公共 API + 显式 `__all__`（get_client_and_config/get_async_client_and_config/RouteConfig/RouteOverride/ROUTES/ROUTES_PATH/get_health_cache/ProviderHealthCache/ProviderState），附「可变全局请操作 `fleetent.model.router` 模块属性」注释；`from fleetent.model import get_client_and_config` 自检通过

## 3. 旧路径 shim

- [x] 3.1 旧 `model_router.py`、`provider_health.py` 改为 shim（re-export + `__all__`，不含逻辑）；`uv run python -c "from fleetent.model_router import get_client_and_config, ROUTES"` 旧路径自检通过

## 4. 改 src 调用方到新公共 API

- [x] 4.1 `agent_loop.py`、`server.py`、`context_mgr.py`、`intelligence/memory/extraction.py`、`observability/startup_diagnostics.py` 改 `from fleetent.model import ...`；`uv run python -c "import fleetent.server, fleetent.agent_loop, fleetent.context_mgr"` 导入成功

## 5. 测试 import + patch 目标随迁

- [x] 5.1 `grep -rn "model_router\|provider_health" tests` 全量核对：`monkeypatch.setattr(model_router, "ROUTES_PATH"/"ROUTES", ...)`、`patch("fleetent.model_router.AsyncOpenAI/OpenAI")` 等模块属性 patch **全部改到 `fleetent.model.router`**；patch 调用方命名空间（`fleetent.agent_loop.*` 等）的测试不动
- [x] 5.2 跑 model 相关测试子集绿（test_model_router、test_provider_health 等）

## 6. 全量门禁 + 文档

- [x] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿（与基线一致）
- [x] 6.2 `uv run ruff format` 本 change 文件 + `ruff check src tests` 干净；`mypy src` 不新增错误模式
- [x] 6.3 更新 `docs/architecture.md`：model 从平铺改记为 `model/`
