## Why

`agent_loop.py` 的 `_call_with_fallback` / `_stream_with_fallback`（行 74 / 102）按 `models_to_try = [cfg.model, *cfg.fallbacks]` 顺序遍历，仅在收到 `RateLimitError`（429）或 `APIStatusError` 503 时切到下一个 provider。问题是：一个 provider 一旦持续故障（连续 429/503 或连接超时），**每次请求仍会先打它、等它失败再 fallback**，白白消耗超时时间，放大用户侧延迟。docs/capabilities/model-router.md「规划中（v1.0）」的 `健康探针缓存` 正是为此：provider 连续失败后标记为暂时不可用，fallback 时跳过它，冷却期满再重新尝试。

## What Changes

- 新增**provider 健康状态缓存**：记录每个 provider（按 model 标识）的连续失败次数与「不可用截止时间」。
- 引入**失败阈值 + 冷却时间**两个旋钮：provider 连续失败达阈值时标记为暂时不可用，持续一段冷却时间；冷却期内 fallback 遍历**跳过**该 provider，避免每次都等超时。
- 冷却期满后该 provider 重新进入候选（半开探测）：再次尝试，成功则清零失败计数恢复可用，失败则重新进入冷却。
- 任一**成功调用**立即将该 provider 失败计数重置为零并清除不可用标记。
- 健康状态缓存**不使用全局可变状态**：封装为可注入实例（`ProviderHealthCache`），通过 monkeypatch 注入测试隔离，沿用项目「模块级单例可替换」模式。
- 失败阈值与冷却时间**支持部署级配置**：在 `config.py` 的 `Settings` 增加 env 字段（沿用 `context_*` / `permission_gate_*` / `agent_*` 既有模式），并支持构造参数覆盖。
- 当一轮 fallback 遍历中**所有候选都被跳过/失败**时，行为与现状一致：抛出最后一个异常，由 agent_loop 上层处理（不静默丢失）。
- **依赖 AR5（error-classification），排其后实施**：失败判定复用 `classify(exc).should_switch_model`（429/503），不自定义异常判定；连接/超时断路留待 AR5 增设连接分类后经 classify 自动覆盖（本次仅 429/503）。

## Capabilities

### New Capabilities
- `provider-health-probe`: 缓存各 provider 连续失败状态，连续失败达阈值后在冷却期内的 fallback 遍历中跳过该 provider；冷却期满半开重试；成功即恢复。阈值与冷却时间可配置，状态缓存可注入（无全局可变状态）。

### Modified Capabilities
<!-- model-router 尚无既有 spec 文件，task_type 路由 / client 无状态等既有行为不变；fallback 遍历的「跳过不健康 provider」新行为收口在新 capability provider-health-probe 内。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/provider_health.py`（`ProviderHealthCache` + `ProviderState` 数据类 + `_default_config()`）。
  - 修改 `src/fleetent/agent_loop.py`：`_call_with_fallback` / `_stream_with_fallback` 遍历前过滤掉冷却期内 provider；每个 model 调用成功 → `cache.record_success(model)`，失败（**复用 AR5 `classify(exc).should_switch_model` 为真者**，即 429/503）→ `cache.record_failure(model)`；全部跳过/失败时仍抛最后异常。
  - 健康缓存实例为模块级可替换单例（同 `session_mgr` 等模式），测试 monkeypatch 注入。
- **配置**：`config.py` 的 `Settings` 增加 `provider_failure_threshold: int = 3`、`provider_cooldown_seconds: int = 60`（env 可配，沿用 `agent_max_*` 模式）；`provider_health.py` 经 `_default_config()` 惰性读取 Settings；构造参数 > Settings > 字段默认值。
- **测试**：新增 `tests/test_provider_health.py`（阈值/冷却/半开/恢复纯逻辑，时间用可注入 `now` 函数或 monkeypatch，不 sleep）；`tests/test_agent_loop.py` 补充「不健康 provider 被跳过」「冷却期满半开重试」用例。LLM 调用按规范 mock（`AsyncOpenAI` 抛 `RateLimitError` / `APIStatusError(503)`），不发真实请求。
- **不影响**：task_type 路由、client 无状态、`RouteConfig` / `ROUTES` 结构、非 429/503 异常的直接 re-raise 语义；不引入新依赖、不引入 AI 框架/ORM/全局可变状态。
