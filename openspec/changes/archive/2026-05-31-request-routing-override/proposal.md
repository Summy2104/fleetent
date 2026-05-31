## Why

`model_router.py` 当前只能按 `task_type` 查 `ROUTES` 表得到 `RouteConfig`，`agent_loop.py` 的 `run()` / `run_stream()` 始终硬编码调用 `get_async_client_and_config("default")`，没有任何在单次调用级别指定模型的能力。调用方若想临时让某次任务走更便宜/更快的模型（如总结、提取、子 agent 走 `claude-haiku-4-5`），只能新增 task_type 或改 `ROUTES`，无法做到「同一 task_type、本次调用临时换模型」。这是 docs/capabilities/model-router.md「规划中（v1.0）」里 `请求级路由覆盖` 的缺口，也是后续成本感知路由、子 agent 降级的前置能力。

## What Changes

- 新增**请求级路由覆盖**：`get_async_client_and_config` / `get_client_and_config` 接受一个可选 `override` 参数，调用方可在单次调用直接指定模型（以及可选 `base_url` / `max_tokens` / `api_key_env`），跳过 `task_type → RouteConfig` 的映射结果中的对应字段。
- 引入 `RouteOverride` 数据类（`frozen dataclass`，字段全部可选）承载覆盖意图，避免在 router 接口上堆叠多个散参数。
- 覆盖语义为**字段级 merge**：override 中非 None 的字段覆盖 `RouteConfig` 对应字段，None 字段沿用 task_type 路由结果；fallbacks 默认清空（强制指定模型时不再走原 fallback 链，除非显式提供）。
- `agent_loop.py` 的 `run()` / `run_stream()` 增加可选参数 `force_model: str | None`，向下透传为 `RouteOverride(model=force_model)`；为 None 时行为与现状完全一致。
- 覆盖后的最终模型写入运行日志（trace），便于事后核对「本次实际用了哪个模型」。

## Capabilities

### New Capabilities
- `request-routing-override`: 在单次 LLM 调用时按字段覆盖 task_type 路由结果（模型、base_url、max_tokens 等），跳过映射；为 None 时保持现状。覆盖意图由 `RouteOverride` 承载，最终模型写入 trace。

### Modified Capabilities
<!-- model-router 尚无既有 spec 文件，task_type 路由 / fallback / client 无状态等既有行为本次不变；新行为收口在新 capability request-routing-override 内。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/model_router.py`：新增 `RouteOverride` 数据类；`get_async_client_and_config` / `get_client_and_config` 增加可选 `override: RouteOverride | None = None`，按字段 merge 到 `RouteConfig` 后再实例化 client。
  - 修改 `src/fleetent/agent_loop.py`：`run()` / `run_stream()` 增加 `force_model: str | None = None`，组装 `RouteOverride` 并透传给 `get_async_client_and_config`；`models_to_try` 在指定 override 时仅含覆盖后的单一模型。
  - `eval_logger.log_run` 已有 `model_used` 字段，覆盖后传入实际模型即可，无需新增字段。
- **配置**：无新增 env / 依赖。`ROUTES` 表与 `Settings` 不变。
- **测试**：新增 `tests/test_model_router.py` 覆盖 override merge / fallbacks 语义；`tests/test_agent_loop.py` 补充 `force_model` 透传用例。LLM 调用按规范 mock（`AsyncOpenAI` 构造 mock、`patch get_async_client_and_config`），不发真实请求。
- **不影响**：task_type 路由、fallback 链遍历、client 无状态（每次新建）、`memory_extraction` 等既有 route；不引入新依赖、不引入 AI 框架/ORM/全局可变状态。
