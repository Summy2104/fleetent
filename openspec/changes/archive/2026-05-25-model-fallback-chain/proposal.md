## Why

`model_router` 目前只有两条硬编码路由，没有任何降级机制。当 Anthropic 出现 429（限速）或 503（服务不可用）时，用户请求直接失败，无法降级到备用模型或 provider，是线上单点故障风险。

## What Changes

- `RouteConfig` 新增 `fallbacks: list[str]` 字段，指定有序的备用模型列表
- `model_router.get_async_client_and_config()` 改为接受 `attempt` 参数，按顺序返回主模型或第 N 个 fallback
- `agent_loop` 在收到 429/503 时自动重试下一个 fallback，直到耗尽或成功
- `config/settings.yaml` 支持 `model_fallbacks` 覆盖默认 fallback 链（可选）
- `eval_logger` 在 trace 中记录实际使用的模型（含 fallback 信息）

## Capabilities

### New Capabilities

- `model-fallback`: LLM 调用失败时按优先级自动切换到备用模型/provider，支持 429 和 503 降级

### Modified Capabilities

- `agent-definition`: `RouteConfig` 结构变更（新增 `fallbacks` 字段），agent 定义中可指定模型 fallback 链

## Impact

- **代码**：`model_router.py`（主要改动）、`agent_loop.py`（重试逻辑）、`config.py`（可选 settings 字段）、`eval_logger.py`（记录实际模型）
- **配置**：`config/settings.yaml` 可选新字段 `model_fallbacks`
- **依赖**：无新依赖
- **破坏性**：无，`fallbacks` 字段可选，默认空列表，现有行为不变
