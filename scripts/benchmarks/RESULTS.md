# fleetent 性能 Benchmark 结果

> 复现:`uv run python scripts/benchmarks/ttft_bench.py --iters 300 --warmup 30 --concurrency 1 4 16 64`
> 环境:隔离临时 FLEETENT_HOME,仅桩掉 LLM 客户端(`_build_async_client`)与 post-reply 记忆抽取;其余框架逻辑(路由/上下文构建/prompt 组装/消息 hygiene/流式管道)真实运行。

## A1. 框架自身 TTFT 开销(排除模型推理)

`--model-delay 0`,即测框架在"首字之前"贡献的纯开销。机器:Darwin arm64,Python 3.12。

| 并发 | TTFT mean | TTFT p50 | TTFT p90 | TTFT p99 | TTFT max |
|------|-----------|----------|----------|----------|----------|
| 1    | 1.35ms    | 1.32ms   | 1.66ms   | 1.99ms   | 2.59ms   |
| 4    | 5.41ms    | 5.43ms   | 7.00ms   | 9.03ms   | 11.73ms  |
| 16   | 19.11ms   | 19.10ms  | 24.98ms  | 27.92ms  | 29.78ms  |
| 64   | 82.73ms   | 83.45ms  | 111.90ms | 128.77ms | 130.86ms |

**结论**:
- 单请求框架首字开销 **p50 ≈ 1.3ms / p99 < 2ms** —— 路由 + 上下文构建 + prompt 组装 + 流式管道的总和。
- 并发下近线性增长:单 asyncio 事件循环,per-request 设置以同步为主,故 N 路并发 ≈ N × 单请求开销。这是可解释、可优化的真实特征(后续可用线程/进程池卸载同步段改善)。

## A2. 端到端 TTFT(含真实模型)

复现:`BENCH_E2E=1 uv run python scripts/benchmarks/ttft_bench.py --iters 12 --warmup 2`
模型:claude-opus-4-8,经 relay(`newapi`);samples=12。

| 指标  | mean     | p50      | p90      | p99      | max      |
|-------|----------|----------|----------|----------|----------|
| TTFT  | 2048ms   | 1971ms   | 2353ms   | 3092ms   | 3184ms   |
| TOTAL | 2723ms   | 2421ms   | 3673ms   | 3844ms   | 3864ms   |

**结论**:
- 端到端首字 p50 ≈ 1.97s,由 **模型推理 + relay 网络主导**。
- 对比 A1(框架 p50 1.3ms):**框架自身开销占端到端首字延迟 < 0.1%**,即框架几乎不引入延迟,瓶颈在模型端点。
- TTFT 强依赖模型选型(opus 偏大);换小模型会显著降低,但不属于框架的工程贡献。

> 注:e2e 曾因 benchmark 未加载 agent 的 `models` 配置而退回默认 Ollama 端点(localhost:11434)导致 ConnectError,已修(显式加载 `ModelPolicySnapshot.from_agent` 并注入 run_stream)。

## 说明(面试可辩护口径)

- A1 是**框架自身**开销,不含模型推理与网络,完全可复现,隔离出工程贡献。
- 端到端首字延迟由模型端点主导;框架仅贡献毫秒级开销。
- 记忆抽取是回复**之后**的后台 best-effort 工作,不在 TTFT 路径上,故基准中 no-op。
