## Context

`build_context()`（[long_term_ctx/__init__.py:134](../../../src/fleetent/long_term_ctx/__init__.py#L134)）在每次 agent 回复**之前**同步构建长期上下文，三路检索顺序 `await`：

```python
memories = await memory.search_facts(user_id, query, limit=_MEMORY_LIMIT)        # L165
knowledge_results = await _search_knowledge(user_id, query, agent_id, ...)        # L166
agent_memory_results = await agent_memory.search_agent_memory(query, ...)         # L174
```

每路内部都会发一次 embedding 请求到外部代理（`jina-embeddings-v3 @ newapi.elevatesphere.com`）。该代理无 SLA、偶发挂起。顺序 await 的后果：(1) 正常延迟是三路之和；(2) 任一路挂起，整个 `build_context` 阻塞到接近底层超时（实测 `agent_run.elapsed_s=185s`）。因为 `build_context` 在回复路径上游，单点抖动 = 用户侧三分钟无响应。

约束：`long_term_ctx` 是 agent 运行时模块，MUST NOT import `fleetent.platform.*`；不得改 `build_context` 公共签名；三路各自的检索语义与合并/预算逻辑（`_select_candidates` 等）保持不变。

## Goals / Non-Goals

**Goals:**
- 三路检索并发执行，正常延迟从"三路之和"降为"最慢一路"。
- 单路超时兜底，使 `build_context` 最坏延迟从"无界（依赖外部代理）"收敛到"约一个超时窗口"。
- 单路失败/超时隔离：一路挂了不拖垮另外两路、不抛异常。
- 分段计时可观测：哪一路慢、是否超时，从日志可直接判定。

**Non-Goals:**
- 不改回复后的 memory 写 pipeline（`run_pipeline_from_conversation`，独立关注点）。
- 不改三路检索各自内部实现，也不改 embedding 客户端/代理选型。
- 不改 `build_context` 入参/出参或 `BuiltContext` 结构。
- 不引入重试（超时即降级，重试留作后续）。

## Decisions

### 决策 1：用 `asyncio.gather(..., return_exceptions=True)` 并发三路

三路彼此无数据依赖，天然可并发。用 `gather` 而非 `TaskGroup`：`TaskGroup` 任一子任务异常会取消其余子任务，与"一路失败不影响其他路"的目标相悖；`gather(return_exceptions=True)` 让每路独立成败，正好。

替代方案：保持顺序但加全局超时——否决，全局超时只能截断总时长，无法让正常路与挂起路并行，正常路仍白等。

### 决策 2：每路包一层 `asyncio.wait_for(coro, timeout)` + 降级

为每路检索包一个 helper：`wait_for` 超时或检索内部抛异常 → 返回该路空结果 + 记 `warning`。超时窗口由配置 `retrieval_timeout_seconds`（默认 5s）控制。降级为空结果后，下游合并逻辑天然把"空结果路"等价于"该路无命中"，无需改 `_select_candidates`。

`agent_memory` 现有的 `except RuntimeError`（backend 未接线降级为空，[L177](../../../src/fleetent/long_term_ctx/__init__.py#L177)）并入统一降级 helper，行为不变。

### 决策 3：分段计时用 `time.monotonic()` 包每路 + 结构化日志

每路 helper 内用 `time.monotonic()` 量耗时，连同路名、是否超时、命中数记一条结构化日志（`get_logger("long_term_ctx")`）。不新增 trace schema，复用现有结构化日志底座即可满足"事后判定哪路慢"。

### 决策 4：超时配置归 `LongTermContextSettings`

`retrieval_timeout_seconds: float = 5.0` 加到 `LongTermContextSettings`，经 `_ltc_config()` 读取。默认 5s 的依据：实测单路 embedding+检索正常 ~1s，5s 给足正常波动余量，又远小于现状的分钟级阻塞。可注入便于测试（unit 用极小超时触发降级分支）。

## Risks / Trade-offs

- **[超时过短误杀正常检索]** → 默认 5s 远高于实测正常延迟（~1s）；可配置，部署侧可按代理实况上调。
- **[并发放大瞬时请求峰值]** 三路同时打 embedding 代理，瞬时并发 ×3 → 量级极小（每次 3 个请求），代理本可承受；收益（消除分钟级阻塞）远大于此风险。
- **[超时降级导致上下文缺失]** 某路超时则本轮该源内容缺失，回复质量轻微下降 → 可接受：现状是"整体卡 3 分钟"，降级换"快速但偶尔少一源"明显更优；warning 日志使缺失可观测、可追因。
- **[gather 吞掉真实异常]** `return_exceptions=True` 可能掩盖检索内部 bug → helper 中对非超时异常也记 warning（含异常类型），不静默吞。

## Migration Plan

纯内部行为改造，无 schema/接口变更，无数据迁移。部署即生效；回滚 = 还原 `build_context` 与配置项。新增配置项有默认值，存量部署无需改配置。
