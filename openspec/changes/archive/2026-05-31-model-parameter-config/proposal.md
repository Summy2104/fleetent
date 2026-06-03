## Why

`model_router.py` 的 `RouteConfig` 当前只有 `max_tokens` 一个生成参数，`agent_loop.py` 的 `_call_with_fallback` / `_stream_with_fallback` 调用 `client.chat.completions.create()` 时也只传 `max_tokens`，temperature / top_p 等采样参数全部交给 provider 默认值。这意味着无法按 `task_type` 区分采样行为——`memory_extraction` 这类抽取任务想要低 temperature（稳定、确定性输出），`default` 对话任务想要更高 temperature（多样性），目前都做不到；调用方也无法在单次调用临时调整采样参数。这是 docs/capabilities/model-router.md「规划中（v1.0）」里 `按 task_type 配置采样参数` 的缺口，也是后续模型选型与质量调优的前置能力。

本 change **依赖** `request-routing-override`（以下简称 MR1，请求级路由覆盖），排在其后：MR1 已新增 `RouteOverride` frozen dataclass、纯函数 `_apply_override(cfg, override)` 与 `get_(async_)client_and_config` 的 `override` 参数；本 change 在这套机制上扩展采样参数维度，不重复造覆盖入口。

## What Changes

- 在 `RouteConfig` 新增 `params: dict[str, Any]` 字段（`field(default_factory=dict)`），承载 per task_type 的默认采样参数（如 `temperature` / `top_p`），与一等字段 `max_tokens` 并列但相互独立。
- 在 MR1 已建的 `RouteOverride` 新增 `params: dict[str, Any]` 字段，承载单次调用的采样参数覆盖。
- 扩展 MR1 已建的 `_apply_override(cfg, override)`：对 `params` 做**深合并**——override 的键替换 base `RouteConfig.params` 中的同名键，未被覆盖的键沿用 base，得到 effective `params`。
- `agent_loop.py` 的 `_call_with_fallback` / `_stream_with_fallback` 在调用 `create()` 时把 effective `params` 透传：`create(model=..., messages=..., tools=..., max_tokens=cfg.max_tokens, **cfg.params)`。`max_tokens` 保持一等字段，不并入 `params`。
- 优先级固定为**调用覆盖 params > task_type params > provider 默认（不传即默认）**。

## Capabilities

### New Capabilities
- `model-parameter-config`: 按 task_type 配置默认采样参数（`RouteConfig.params`），并支持单次调用经 `RouteOverride.params` 深合并覆盖；effective `params` 透传给 `create()`。优先级为调用覆盖 > task_type > provider 默认；`max_tokens` 保持一等字段不并入 `params`。

### Modified Capabilities
<!-- request-routing-override（MR1）的覆盖入口、字段级 merge、覆盖模型清空 fallback 等需求级行为本次不变；本 change 在 `_apply_override` 上**新增** params 深合并维度，属能力扩展而非既有需求变更，收口在新 capability model-parameter-config 内。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/model_router.py`：`RouteConfig` 新增 `params: dict[str, Any] = field(default_factory=dict)`；`RouteOverride`（MR1 已建）新增 `params: dict[str, Any] = field(default_factory=dict)`；`_apply_override`（MR1 已建）增加 `params` 深合并逻辑。
  - 修改 `src/fleetent/agent_loop.py`：`_call_with_fallback` / `_stream_with_fallback` 在 `create()` 调用处追加 `**cfg.params`（位于 `max_tokens=cfg.max_tokens` 之后）。
  - `eval_logger.log_run` 不变——采样参数不入 trace schema（如需可后续 change）。
- **配置**：无新增 env / 依赖。`ROUTES` 表的既有 entry 不强制填 `params`（默认空 dict ⇒ 行为与现状逐字节一致）；可按需为 `memory_extraction` 等 entry 补 `params`。
- **测试**：扩展 `tests/test_model_router.py` 覆盖 `RouteConfig.params` 默认值、`RouteOverride.params` 深合并、`_apply_override` params 语义；`tests/test_agent_loop.py` 补充 `create()` 收到 `**params` 的透传用例。LLM 调用按规范 mock（`AsyncOpenAI` 构造 mock / `patch get_async_client_and_config`），不发真实请求。
- **不影响**：task_type 路由、fallback 链遍历、client 无状态（每次新建）、`max_tokens` 既有处理、MR1 的覆盖入口/字段级 merge/清空 fallback 语义；不引入新依赖、不引入 AI 框架/ORM/全局可变状态。
