## 1. model_router — RouteConfig fallbacks 字段

- [x] 1.1 Write failing tests: `RouteConfig` 默认 `fallbacks=()` ；显式传入 `fallbacks=("haiku",)` 后字段可读；frozen dataclass 约束不变
- [x] 1.2 在 `RouteConfig` 添加 `fallbacks: tuple[str, ...] = ()`，确保测试通过

## 2. agent_loop — 非流式 fallback 重试

- [x] 2.1 Write failing tests: 主模型 429 时自动切换到第一个 fallback；503 同样触发切换；所有 fallback 耗尽后抛最后一个异常；401 不触发 fallback 直接抛出
- [x] 2.2 在 `agent_loop.run()` 中提取 `_llm_call_with_fallback(client, cfg, messages, schemas)` 辅助函数，实现 fallback 重试逻辑（捕获 `RateLimitError` 和 `APIStatusError` status 503），替换原有 LLM 调用

## 3. agent_loop — 流式 fallback 重试

- [x] 3.1 Write failing tests: `run_stream()` 中主模型 429 → 切换 fallback 继续 yield；fallback 耗尽后 yield error event
- [x] 3.2 在 `agent_loop.run_stream()` 中同样应用 fallback 逻辑（流式版本：fallback 发生在 `await client.chat.completions.create(..., stream=True)` 调用处，stream 尚未产生任何 chunk，重试安全）

## 4. eval_logger — 记录实际使用的模型

- [x] 4.1 Write failing tests: fallback 发生时 trace 中 `model_used` 为 fallback 模型名；无 fallback 时为主模型名
- [x] 4.2 在 `eval_logger.log_run()` 添加可选 `model_used: str | None = None` 参数并写入 trace；在 `agent_loop` 两处调用 `log_run()` 时传入实际使用的模型名

## 5. 验证

- [x] 5.1 运行完整测试套件（`uv run pytest -x -q`），确认全部通过
- [x] 5.2 手动验证：配置 `fallbacks=("claude-haiku-4-5",)` 并 mock 主模型 429，确认切换到 haiku 且 trace 中 `model_used` 正确
