## Why

`build_context()` 的三路检索（memory / knowledge_base / agent_memory）当前在 [long_term_ctx/__init__.py](../../../src/fleetent/long_term_ctx/__init__.py) 里**顺序 `await`**，每路各发一次 embedding 请求到外部代理（jina@newapi）。该代理无 SLA、偶发请求挂起：单路卡住会让整个 `build_context` 阻塞到接近超时（实测 `agent_run.elapsed_s = 185s`，Slack spinner 转 3 分钟）。由于 `build_context` 在回复返回之前同步执行，单点检索抖动直接体现为用户侧"三分钟无响应"。

## What Changes

- 三路检索（memory / knowledge / agent_memory）由顺序 `await` 改为 **`asyncio.gather` 并发**，整体延迟由"三路之和"降为"最慢一路"。
- 每路加**单路超时兜底**（可配置，默认 5s）：超时则该路降级为空结果、记 `warning`，不阻塞其余两路、不拖垮整体。三路并发 + 单路超时使 `build_context` 最坏延迟从"无界（依赖代理）"收敛到"约一个超时窗口"。
- 加**分段计时**：每路检索耗时与是否超时记入 trace / 结构化日志，使"哪一路慢、是 embedding 还是向量查"可从日志直接判定，无需复现。
- 新增配置项 `retrieval_timeout_seconds`（归 long-term-ctx 配置命名空间），控制单路超时。

非目标：不改 `build_context` 入参/出参签名；不改回复后的 memory 写 pipeline（独立关注点）；不改三路各自的检索语义与预算合并逻辑。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `long-term-ctx`: 新增"检索韧性"要求——三路检索 SHALL 并发执行、各路 SHALL 受单路超时约束、超时路 SHALL 降级为空结果并记 warning；现有"三类源合并与预算"语义不变（超时路等价于该路返回空）。

## Impact

- **owning package**: `long_term_ctx`
- **public API surface**: `build_context()` 签名与返回 `BuiltContext` 不变（纯内部并发/超时改造）
- **owned tables**: 无
- **config namespace**: `long-term-ctx`（新增 `retrieval_timeout_seconds`，落 `LongTermContextSettings`）
- **cross-module dependencies**: 继续依赖 `memory.search_facts` / `knowledge_base.retrieval.search` / `memory.search_agent_memory` 的 public API，不新增共享契约
- **migration / shim plan**: 无（不移动模块、不改 import 路径）
- **affected code**: [long_term_ctx/__init__.py](../../../src/fleetent/long_term_ctx/__init__.py) `build_context`、`config.LongTermContextSettings`、对应 unit 测试
