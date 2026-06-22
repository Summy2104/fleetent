## Why

实测 managed 全链路时发现:命名 agent 经控制面配模型后,只要 `model_overrides` **没显式给 `embedding` 路由**,`fleetent agent run` 在 **boot 阶段直接崩**——`vector_store.configure_from_active_agent()` → `create_embedding_provider_from_policy()` → `policy.resolve("embedding")` 抛 `ModelConfigError: model route 'embedding' is not configured`。

但无名 agent(`agent.name == ""`)本来就回落 `DeterministicEmbeddingProvider`、永远能 boot。也就是说:**chat-only 的命名 managed agent 被强制要求配 embedding provider,否则起不来**,而 embedding 只有 KB / 向量检索 / memory 才真正用到。运维配漏一条路由 = agent 起不来,控制面零提示。这是 managed agent "真能跑起来" 链路上的一个健壮性缺口。

## What Changes

- `vector_store._configure`:命名 agent **缺少 `embedding` 路由时回落 `DeterministicEmbeddingProvider` + 记 WARN 日志**,而不是抛错崩 boot——与无名 agent 的既有回落行为对齐。
- WARN 日志明确告知:未配 embedding 路由、已用 deterministic 回落、KB/向量检索质量会退化、生产应显式配 embedding 路由。
- agent 显式配了 `embedding` 路由时行为不变(走 `HttpEmbeddingProvider`)。
- **非破坏性**:只把"硬崩"换成"降级 + 告警";已正确配 embedding 的 agent 零影响。

## Capabilities

### New Capabilities
<!-- 无新增独立 capability -->

### Modified Capabilities
- `vector-store`: 新增「configure 时缺 embedding 路由 → deterministic 回落而非崩」的行为要求。

## Impact

- `src/fleetent/vector_store/runtime.py` — `_configure` 增加缺路由检测 + deterministic 回落 + WARN。
- `src/fleetent/vector_store/embeddings.py` — 不改(`create_embedding_provider_from_policy` 仍负责显式路由;回落判断在 `_configure`)。
- owning package = `vector_store`(独立基础设施组件,**不碰 platform**,符合依赖方向约束)。
- 测试:命名 agent 无 embedding 路由 → configure 不抛、`_embedding` 为 deterministic;有 embedding 路由 → 走 http provider。
- 文档:`vector-store` 行为说明同步;managed agent 模型配置文档提示 embedding 路由可选但生产应配。
