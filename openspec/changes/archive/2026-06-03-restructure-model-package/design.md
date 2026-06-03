## Context

蓝图已确立目标结构；sandbox / session / skills 范式在前。现状：`model_router.py`（路由表、YAML 外置、override、client 工厂，约 260 行）+ `provider_health.py`（熔断缓存，约 110 行，仅被 agent_loop 引用）平铺。

src 直接调用方（已扫描）：
- `agent_loop.py`：`get_async_client_and_config, get_client_and_config, RouteConfig, RouteOverride` + `get_health_cache, ProviderState`
- `server.py` / `context_mgr.py` / `intelligence/memory/extraction.py` / `observability/startup_diagnostics.py`：`get_client_and_config` 系 + `ROUTES`

测试 patch 面（已扫描）：`test_model_router.py` 直接 patch `fleetent.model_router.{AsyncOpenAI, OpenAI}` 与 `monkeypatch.setattr(model_router, "ROUTES_PATH", ...)`、`ROUTES` 表注入；全库其余 LLM mock 多 patch 调用方命名空间（`fleetent.agent_loop.*`、`fleetent.memory_layer.get_client_and_config` 等），不在本包受影响面内。

## Goals / Non-Goals

**Goals**：2 文件迁入 `model/`、去前缀、`__init__` 收口、调用方改新路径、shim 兜底、patch 目标随迁、全量绿、行为不变。
**Non-Goals**：不改路由解析 / fallback / 参数合并 / 缓存（`(path, mtime, size)` parse cache）逻辑；不改 routes.yaml 契约；不动调用方对返回值的使用方式。

## Decisions

### D1 — 文件映射
```
model_router.py    → model/router.py
provider_health.py → model/provider_health.py   # 无前缀可去，仅移动
```
`git mv` 保留历史。

### D2 — 公共 API 收口 `model/__init__.py`
`get_client_and_config, get_async_client_and_config, RouteConfig, RouteOverride, ROUTES, ROUTES_PATH`（router）+ `get_health_cache, ProviderHealthCache, ProviderState`（provider_health）。`__all__` 显式。注意 `ROUTES` / `ROUTES_PATH` 是**可变模块全局**：包级 re-export 的是引用副本，**调用方与测试一律操作 `fleetent.model.router` 模块属性**，不通过包级名 monkeypatch（写入 README 注释于 `__init__.py`）。

### D3 — 旧路径 shim
`model_router.py` / `provider_health.py` 改为 re-export shim + `__all__`，不承载逻辑。

### D4 — 可变全局的 patch 纪律（本包特有风险）
`ROUTES_PATH` / `ROUTES` 被测试大量 `monkeypatch.setattr(model_router, ...)`。shim 上的 setattr 不会作用到真实模块（import * 复制引用）。因此 `test_model_router.py` 等**所有 setattr/patch 模块属性的测试必须改为操作 `fleetent.model.router`**。grep 核对：`monkeypatch.setattr(model_router` / `patch("fleetent.model_router`。

### D5 — provider_health 不设独立 shim 例外
它同样留 shim（与约定一致），尽管 src 内仅 agent_loop 引用——测试可能直接 import。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 可变全局 patch 漂移（ROUTES/ROUTES_PATH） | D4 强制随迁；全量 pytest 暴露未生效的 patch |
| parse cache 键含 path——路径语义不变 | `ROUTES_PATH` 仍是 CWD 相对 `config/routes.yaml`，无 `__file__` 依赖，移动无影响 |
| import 改漏 | shim 兜底 + 全量 pytest + 自检 |
| `_RESERVED_PARAM_KEYS` 等私有名被测试触达 | 测试改从 `fleetent.model.router` import 私有名 |

## 验收

- `model/` 成包，`__init__.py` 收口公共 API，`__all__` 显式（含可变全局使用注释）。
- 旧 2 文件仅 re-export（无逻辑）。
- 5 处 src 调用方从 `fleetent.model` 导入。
- 无测试 monkeypatch 旧 shim 路径的模块属性。
- 全量 pytest 绿；ruff 干净；mypy 不新增错误模式。
- 自检：`from fleetent.model import get_client_and_config, RouteConfig, get_health_cache` 成功；旧路径 import 仍可用。
