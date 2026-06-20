## Context

`vector_store/runtime.py` 的 `_configure(agent)`:
```python
if not agent.name:
    _embedding = DeterministicEmbeddingProvider()        # 无名 agent:永远能 boot
else:
    _embedding = create_embedding_provider_from_policy(   # 命名 agent:缺 embedding 路由就抛
        ModelPolicySnapshot.from_agent(agent))
```
`create_embedding_provider_from_policy` → `policy.resolve("embedding")` → `routes` 里没有 `"embedding"` 键就 `raise ModelConfigError("model route 'embedding' is not configured")`。该调用在 `agent_app.boot()` 早期(`configure_from_active_agent()`),抛错 = 整个 `fleetent agent run` 崩。

embedding 的真实消费方都是**后置/按需**的:`memory/*`(post-turn 抽取与检索)、`knowledge_base/*`(ingest/retrieval)。chat-only 一问一答不需要可用的 embedding;实测后置 memory embedding 打到未配端点 404 也被上层容忍、不影响对话完成。

## Goals / Non-Goals

**Goals:**
- 命名 chat-only managed agent **缺 embedding 路由也能 boot**。
- 缺路由时**可见地降级**(WARN),不静默。
- 已显式配 embedding 路由的 agent 行为零变化。

**Non-Goals:**
- 不改 embedding provider 抽象 / `HttpEmbeddingProvider` / `create_embedding_provider_from_policy` 的显式路径。
- 不把 embedding 改成完全惰性配置(更大重构,本 change 不做)。
- 不动 KB/memory 调用点的容错逻辑。
- 不在控制面 / materialize 侧加路由完整性校验(可作后续;本 change 只让运行时健壮)。

## Decisions

**D1 — 缺路由回落 `DeterministicEmbeddingProvider`,不抛错。** 在 `_configure` 里:命名 agent 且 `"embedding" not in policy.routes` 时,用 `DeterministicEmbeddingProvider()` 并记 WARN;否则走 `create_embedding_provider_from_policy`。判断用 `policy.routes` 成员检查(不靠捕获 `ModelConfigError`,避免把"路由存在但配错"——协议错/缺 endpoint——也一并吞掉:那类**仍应抛**,是真配置错误)。

**D2 — 为什么是 deterministic 而非"用时才报错的 null provider"。** deterministic 是无名 agent 既有回落,行为一致、零新类型;且后置 memory/KB embedding 调用点对失败的容忍度不齐,raise-on-use 可能在某些路径炸 turn。deterministic 让 boot 与后置调用都不炸。代价:agent 若真用 KB 却漏配 embedding,检索质量静默退化——用 **WARN 日志**兜(明确写"已 deterministic 回落、生产请配 embedding 路由")。

**D3 — 协议错/缺 endpoint 仍抛。** 只有"路由完全缺失"才回落;路由存在但 target 协议非 `http_embedding` 或缺 endpoint,仍由 `create_embedding_provider_from_policy` 抛 `ModelConfigError`——那是明确的误配,不该静默降级。

### 模块边界影响(AGENTS.md 要求)

- **owning package**:`vector_store`(独立基础设施组件)。
- **public API surface**:无变化(`configure_from_active_agent()` / `_configure` 签名不变;`upsert`/`search`/`embed_text` 不变)。
- **owned tables**:无。
- **config namespace**:无。
- **cross-module dependencies**:`vector_store` 已依赖 `agent_config`、`model.ModelPolicySnapshot`;无新增。**不 import `platform`**(依赖方向约束不变)。
- **migration / shim plan**:无 schema 迁移、无模块移动、无 shim。

## Risks / Trade-offs

- **静默退化风险**(D2):漏配 embedding 又真用 KB 的 agent,检索拿到 deterministic 假向量、质量差但不报错。缓解:configure 时 WARN 写清后果与修法。比"boot 崩"更可接受——崩是确定性故障,降级+告警是可运维的。
- **WARN 噪声**:每次 boot 一条 WARN。可接受(boot 一次性);且正是要让运维看见。
- **与未来"控制面路由完整性校验"的关系**:本 change 让运行时健壮;若后续在 materialize/apply 侧加"建议配全路由"的校验,二者互补不冲突。
