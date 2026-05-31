## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `_call_with_fallback` / `_stream_with_fallback`（agent_loop.py 行 74 / 102）现有遍历与异常捕获：仅 `RateLimitError` 与 `APIStatusError` 503 触发 fallback，其余 re-raise，全部失败 `raise last_exc`；`models` 来自 `[cfg.model, *cfg.fallbacks]`
- [ ] 1.2 确认 AR5 `error_classifier.classify()` 接口（本 change 依赖 AR5、排其后）：`record_failure` 判据 = `classify(exc).should_switch_model`（即 429/503）；连接/超时断路留待 AR5 增设连接分类后经 classify 自动覆盖，本次不自定义异常判定
- [ ] 1.3 核实 `tests/test_agent_loop.py` 既有「provider 耗尽抛异常」期望，据此固化 D4「全部冷却时不静默失败」的兜底策略

## 2. ProviderState 与 ProviderHealthCache（provider_health.py）

- [ ] 2.1 Write failing tests for `ProviderState` 与 `ProviderHealthCache` 基本结构：`tests/test_provider_health.py` 断言新建缓存对任意 model `is_available` 返回 True、计数为 0；构造参数 `failure_threshold` / `cooldown_seconds` / `now` 可注入假时钟。看到红
- [ ] 2.2 Implement `ProviderState` 数据类与 `ProviderHealthCache`（内部 dict，构造参数 + 可注入 `now`），看到绿

## 3. 失败阈值 → 进入冷却

- [ ] 3.1 Write failing tests：连续 `record_failure` 达 `failure_threshold` 后 `is_available` 在冷却时间内返回 False；未达阈值仍 True；阈值/冷却通过构造参数注入，时间用假时钟推进不 sleep。看到红
- [ ] 3.2 Implement `record_failure`（累计计数，达阈值置 `unavailable_until = now() + cooldown_seconds`）与 `is_available`，看到绿

## 4. 冷却到点半开 + 成功恢复

- [ ] 4.1 Write failing tests：冷却到点后（假时钟推进过 `unavailable_until`）`is_available` 返回 True（半开）；半开后 `record_failure` 再达阈值重入冷却；任一 `record_success` 立即清零计数并清除不可用标记。看到红
- [ ] 4.2 Implement `is_available` 的冷却到点放行与 `record_success`（清零 + 置 `unavailable_until=0`），看到绿

## 5. 配置接入（Settings + _default_config，对齐 termination/context_mgr 模式）

- [ ] 5.1 Write failing tests：`Settings` 含 `provider_failure_threshold`（默认 3）、`provider_cooldown_seconds`（默认 60）；`provider_health._default_config()` 返回二者且可被构造参数覆盖（参数 > config）。看到红
- [ ] 5.2 Implement：`config.py` 的 `Settings` 增加两字段；`provider_health.py` 增 `_default_config()`（惰性 `from fleetent.config import Settings`）+ 缺省构造从 config 取值。看到绿

## 6. 可注入模块单例

- [ ] 6.1 Write failing tests：模块级缓存单例可被 monkeypatch 替换；`agent_loop` 通过该单例访问，替换后互不影响。看到红
- [ ] 6.2 Implement：`provider_health.py` 暴露模块级 `_cache` 单例 + getter（同 session_mgr 风格），看到绿

## 7. 接入 _call_with_fallback（跳过 + 记录）

- [ ] 7.1 Write failing tests（mock `AsyncOpenAI`，首选 model 抛 `RateLimitError`/`APIStatusError(503)`，后续 model 成功）：首选达阈值后处于冷却时遍历跳过它直接试后续；成功 model 触发 `record_success`；4xx 非健康错误直接 re-raise 且不计失败；全部不可用按既有契约抛异常不返回空。看到红
- [ ] 7.2 Implement `_call_with_fallback`：遍历前用 `is_available` 过滤候选；每个 model 成功 `record_success`、`classify(exc).should_switch_model` 为真时 `record_failure`，其余 re-raise；保留全部失败 `raise last_exc`。看到绿

## 8. 接入 _stream_with_fallback

- [ ] 8.1 Write failing tests for `_stream_with_fallback` 健康跳过/记录：行为与 `_call_with_fallback` 一致（跳过冷却 provider、成功恢复、429/503 计失败）。看到红
- [ ] 8.2 Implement `_stream_with_fallback` 接入同一 `ProviderHealthCache` API，看到绿

## 9. 收尾

- [ ] 9.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`）无回归；provider_health 测试全部用假时钟，无真实 sleep
- [ ] 9.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 未新增 mypy 错误模式
- [ ] 9.3 加回归守卫 `test_non_health_status_error_never_marks_unavailable`：401/400 等错误经 fallback 路径后该 provider 仍 `is_available` 为 True
