## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `model_router.py` 现有签名：`get_async_client_and_config(task_type="default") -> (AsyncOpenAI, RouteConfig)`、`get_client_and_config` 同类；`RouteConfig` 为 frozen dataclass，字段 `base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks`
- [ ] 1.2 核实 `agent_loop.py` 调用点：`run()` 行 153 / `run_stream()` 行 314 均 `get_async_client_and_config("default")`；`models_to_try = [cfg.model, *cfg.fallbacks]`（行 169 / 330）；确认 `log_run` 已有 `model_used` 参数无需新增字段
- [ ] 1.3 核实两个 router 函数的 key 处理差异（sync 缺 key 抛 `RuntimeError`，async 用空串），确认本 change 不改该差异

## 2. RouteOverride 数据类（model_router.py）

- [ ] 2.1 Write failing tests for `RouteOverride`：`tests/test_model_router.py` 断言 `RouteOverride` 为 frozen dataclass，字段 `model` / `base_url` / `max_tokens` / `api_key_env` / `fallbacks` 均可选且默认 None。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `RouteOverride`（frozen dataclass，全字段可选默认 None），看到绿

## 3. 字段级 merge 纯函数

- [ ] 3.1 Write failing tests for `_apply_override(cfg, override) -> RouteConfig`：override 为 None 时原样返回 cfg；仅设 `model` 时只替换 model 其余沿用；同时设 `model` + `base_url` 时两者均替换。看到红
- [ ] 3.2 Implement `_apply_override`（按非 None 字段替换，返回新 frozen `RouteConfig`），看到绿

## 4. 覆盖模型清空 fallback 语义

- [ ] 4.1 Write failing tests：base cfg 含非空 fallbacks，override 设 `model` 未设 `fallbacks` 时结果 fallbacks 为空；override 显式设非空 `fallbacks` 时以该值为准；override 为 None 时 fallbacks 不变。看到红
- [ ] 4.2 Implement：在 `_apply_override` 中实现「设 model 且未设 fallbacks ⇒ 清空」与「显式 fallbacks 优先」语义，看到绿

## 5. router 入口接入 override

- [ ] 5.1 Write failing tests for `get_async_client_and_config(..., override=...)` 与 `get_client_and_config(..., override=...)`：mock `AsyncOpenAI` / `OpenAI` 构造，验证传入覆盖意图时 client 用覆盖后的 base_url、返回 cfg.model 为覆盖值；不传 override 时与现状一致。看到红
- [ ] 5.2 Implement：两函数末尾增加 `override: RouteOverride | None = None`，取 base cfg 后经 `_apply_override` 得 effective cfg 再实例化 client，看到绿

## 6. agent_loop run() 接入 force_model

- [ ] 6.1 Write failing tests for `run(..., force_model=...)`（patch `get_async_client_and_config`，断言透传的 override）：`force_model=None` 时不传 override 且 `models_to_try` 含 fallbacks；`force_model="claude-haiku-4-5"` 时透传 `RouteOverride(model=...)` 且每轮 LLM 调用用该模型、`models_to_try` 仅含单一模型。看到红
- [ ] 6.2 Implement：`run()` 增加 `force_model: str | None = None`，组装 override 透传，override 生效时 `models_to_try = [cfg.model]`，看到绿

## 7. agent_loop run_stream() 接入 force_model

- [ ] 7.1 Write failing tests for `run_stream(..., force_model=...)`：行为与 `run()` 一致（None 保持现状、非 None 贯穿本次流式调用）。看到红
- [ ] 7.2 Implement：`run_stream()` 增加同名参数并以相同方式透传，看到绿

## 8. trace 记录实际模型

- [ ] 8.1 Write failing tests：以 `force_model` 运行并正常结束时 `log_run` 收到的 `model_used` 为覆盖模型；不传时为 task_type 默认模型。看到红
- [ ] 8.2 Implement：确保 `run()` / `run_stream()` 在收尾时把 effective `model_used` 传入 `log_run`，看到绿

## 9. 收尾

- [ ] 9.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`）无回归
- [ ] 9.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 未新增 mypy 错误模式
- [ ] 9.3 加回归守卫 `test_override_none_is_byte_identical_routing`：override=None 时 `get_async_client_and_config` 返回的 cfg 与不传 override 完全相等（model / base_url / fallbacks 均不变）
