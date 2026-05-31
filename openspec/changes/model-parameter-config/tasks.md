## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 确认 MR1（`request-routing-override`）已落地：`model_router.py` 已有 `RouteOverride` frozen dataclass、纯函数 `_apply_override(cfg, override) -> RouteConfig`、`get_(async_)client_and_config(..., override=None)` 入口；本 change 在其上扩展 `params` 维度，不重建覆盖入口
- [ ] 1.2 核实 `RouteConfig` 现有字段：`base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks`，frozen dataclass；新增 `params: dict[str, Any] = field(default_factory=dict)` 即向后兼容（既有 `ROUTES` entry 不填即空 dict）
- [ ] 1.3 核实 `agent_loop.py` 两个 `create()` 调用点：`_call_with_fallback`（行 85-90）与 `_stream_with_fallback`（行 113-120），二者均传 `max_tokens=cfg.max_tokens`，确认追加 `**cfg.params` 位置在 `max_tokens` 之后；确认 `params` 内不得含 `max_tokens` 键（否则 `create()` 重复 kw 抛 `TypeError`）

## 2. RouteConfig 新增 params 字段（model_router.py）

- [ ] 2.1 Write failing tests for `RouteConfig.params`：`tests/test_model_router.py` 断言 `RouteConfig` 含 `params` 字段、默认为空 dict（`field(default_factory=dict)`）、可在构造时传入采样参数 dict。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：`RouteConfig` 新增 `params: dict[str, Any] = field(default_factory=dict)`（补 `from dataclasses import field`、`from typing import Any`），看到绿

## 3. RouteOverride 新增 params 字段（扩展 MR1）

- [ ] 3.1 Write failing tests for `RouteOverride.params`：断言 MR1 的 `RouteOverride` 含 `params` 字段、默认为空 dict、frozen。看到红
- [ ] 3.2 Implement：`RouteOverride` 新增 `params: dict[str, Any] = field(default_factory=dict)`，看到绿

## 4. _apply_override 的 params 深合并语义（扩展 MR1）

- [ ] 4.1 Write failing tests for `_apply_override` 的 params 深合并：base cfg `params={"temperature":0.7,"top_p":0.9}` + override `params={"temperature":0.0}` ⇒ 结果 `{"temperature":0.0,"top_p":0.9}`（覆盖键替换、未覆盖键沿用）；override 新增 base 中不存在的键 ⇒ 结果含新增键且保留 base 其余键；override `params` 为空 ⇒ 结果 params 等于 base.params；override 为 None ⇒ params 不变。看到红
- [ ] 4.2 Implement：在 `_apply_override` 中以 `{**cfg.params, **override.params}` 计算 effective params 并写入返回的新 frozen `RouteConfig`，看到绿

## 5. params 与 max_tokens 分离的守卫

- [ ] 5.1 Write failing tests：断言内置 `ROUTES` 各 entry 的 `params` 均不含 `max_tokens` 键（守卫 D3 约定——`max_tokens` 保持一等字段，不并入 params，避免 `create()` 重复 kw）。看到红
- [ ] 5.2 Implement：确保内置 `ROUTES` entry 的 `params` 不含 `max_tokens`（不填即空 dict），看到绿

## 6. agent_loop 透传 effective params（_call_with_fallback）

- [ ] 6.1 Write failing tests for `_call_with_fallback`（mock `AsyncOpenAI` 的 `chat.completions.create`）：cfg.params 非空时 `create()` 收到对应采样 kw 且与 `max_tokens` 并存；cfg.params 为空时 `create()` 调用参数集合与现状一致（不含任何采样 kw）。看到红
- [ ] 6.2 Implement：`_call_with_fallback` 的 `create()` 调用在 `max_tokens=cfg.max_tokens` 之后追加 `**cfg.params`，看到绿

## 7. agent_loop 透传 effective params（_stream_with_fallback）

- [ ] 7.1 Write failing tests for `_stream_with_fallback`：行为与 `_call_with_fallback` 一致——cfg.params 透传给流式 `create()` 且与 `max_tokens` / `stream` / `stream_options` 并存；空 params 时调用参数与现状一致。看到红
- [ ] 7.2 Implement：`_stream_with_fallback` 的 `create()` 调用同样追加 `**cfg.params`，看到绿

## 8. 端到端优先级（调用覆盖 > task_type > provider 默认）

- [ ] 8.1 Write failing tests：经 `get_async_client_and_config("default", override=RouteOverride(params={...}))` 得到的 effective cfg 的 `params` 体现深合并结果；override.params 为空时 effective params 等于 task_type 默认 params；无 override 时 params 即 task_type 默认。看到红
- [ ] 8.2 Implement：确认 MR1 的 `get_(async_)client_and_config` 经扩展后的 `_apply_override` 正确产出 effective params（本步通常无新增实现，仅验证链路打通），看到绿

## 9. 收尾

- [ ] 9.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求）无回归
- [ ] 9.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 未新增 mypy 错误模式
- [ ] 9.3 加回归守卫 `test_empty_params_call_is_byte_identical`：cfg.params 为空时 `_call_with_fallback` / `_stream_with_fallback` 传给 `create()` 的 kwargs 集合与未引入 params 前完全一致（不含任何采样 kw）
