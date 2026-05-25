## Context

`model_router.py` 是一个无状态的薄工厂：`RouteConfig` 是 frozen dataclass，`get_async_client_and_config()` 每次调用都创建新客户端（intentional，客户端无状态且廉价）。`agent_loop.run()` 和 `run_stream()` 各自调用一次 `get_async_client_and_config("default")` 获取 `(client, cfg)`，然后在 while 循环中复用。LLM 调用点是 `client.chat.completions.create()`（非流式）和带 `stream=True` 的同名调用（流式）。

当前问题：这两处调用在收到 HTTP 429（rate limit）或 503（service unavailable）时直接向上抛出异常，没有任何降级路径。

## Goals / Non-Goals

**Goals:**
- `RouteConfig` 支持有序 fallback 模型列表
- `agent_loop` 在 429/503 时自动切换到下一个 fallback 模型重试
- 所有 fallback 耗尽后透传最后一个异常
- eval trace 中记录实际使用的模型（含 fallback 发生时）
- 向后兼容：`fallbacks` 为空时行为与现在完全一致

**Non-Goals:**
- 指数退避 / jitter（不同模型间无需 sleep，立即切换）
- 跨 `base_url` 的 provider 切换（fallback 复用主 route 的 `base_url` + `api_key_env`）
- 其他错误码的重试（connection error、401 不触发 fallback）
- `memory_extraction` 路由的 fallback（低优先级，单独配置即可）

## Decisions

### 1. `fallbacks` 用 `tuple[str, ...]` 而非 `list[str]`

`RouteConfig` 是 `frozen=True` dataclass，不能持有可变字段。用 `tuple[str, ...] = ()` 既符合约束又自然表达有序序列。

### 2. 重试逻辑在 `agent_loop` 而非 `model_router`

`model_router` 的职责是"工厂"——给定 task_type 返回客户端和配置，不感知调用上下文。重试是调用层的关注点，放在 `agent_loop` 保持 `model_router` 无状态。

实现：`agent_loop` 在进入 while 循环前构建模型序列 `[cfg.model, *cfg.fallbacks]`，每次 LLM 调用时捕获 429/503，使用 `dataclasses.replace(cfg, model=next_model)` 创建新配置，用新 model 重试。

### 3. 只捕获 429 和 503

- `openai.RateLimitError` → 429，明确的速率限制，换模型有意义
- `openai.APIStatusError` with `status_code == 503` → 服务不可用，换模型有意义
- 其他错误（401、400、connection error）不触发 fallback，直接上抛

### 4. 流式和非流式都包在同一个 fallback 工具函数里

提取 `_call_with_fallback(client, cfg, messages, schemas)` 辅助函数，`run()` 和 `run_stream()` 分别调用对应版本（非流式直接返回 response，流式返回 stream）。避免在两处重复 fallback 逻辑。

### 5. 记录实际使用的模型

`eval_logger.log_run()` 已有 `usage` 参数。在现有结构上新增 `model_used: str` 字段，记录最终成功调用的模型名。fallback 发生时 `model_used != cfg.model`，方便排查。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| fallback 模型能力不同（如 haiku 替代 sonnet），输出质量下降 | 用户配置 fallback 时需自行选择兼容模型；日志中有 `model_used` 可监控 |
| 流式 429 可能已经向客户端 yield 了部分 token，切换后重发会导致重复 | 429/503 在 HTTP 握手阶段返回，stream 对象尚未产生任何 chunk，重试安全 |
| `dataclasses.replace` 每次重试创建新 config 对象 | config 对象极轻量（4 个字段），无性能问题 |

## Migration Plan

1. `RouteConfig` 加字段（向后兼容，默认 `()`）
2. `agent_loop` 加 fallback 辅助函数，替换现有 LLM 调用点
3. `eval_logger` 加 `model_used` 字段（可选，不破坏现有 trace 消费）
4. 无数据迁移，无 API 变更，无配置强制要求
