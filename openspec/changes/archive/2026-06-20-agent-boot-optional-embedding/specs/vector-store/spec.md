## ADDED Requirements

### Requirement: configure 容忍缺失的 embedding 路由
`vector_store.configure_from_active_agent()`(经 `_configure`)在为命名 agent 配置 embedding provider 时,若该 agent 的模型策略**未配置 `embedding` 路由**,SHALL 回落到 `DeterministicEmbeddingProvider` 并记录一条 WARN 日志(说明已回落、KB/向量检索质量将退化、生产应显式配置 embedding 路由),而 SHALL NOT 抛错。这保证 chat-only 的命名 managed agent 在缺 embedding 路由时仍能 boot(与无名 agent 的既有回落行为一致)。

显式配置了 `embedding` 路由的 agent,行为不变(走 `create_embedding_provider_from_policy` → `HttpEmbeddingProvider`)。仅"路由完全缺失"触发回落;路由存在但 target 协议非 `http_embedding` 或缺 endpoint,仍 SHALL 抛 `ModelConfigError`(明确误配,不静默降级)。

#### Scenario: 命名 agent 缺 embedding 路由回落 deterministic
- **WHEN** 一个命名 agent 的模型策略不含 `embedding` 路由,调用 `configure_from_active_agent()`
- **THEN** 不抛错,配置的 embedding provider 为 `DeterministicEmbeddingProvider`
- **AND** 记录一条 WARN 日志提示已回落且生产应配置 embedding 路由

#### Scenario: 命名 agent 已配 embedding 路由走 http provider
- **WHEN** 一个命名 agent 显式配置了 `http_embedding` 协议、含 endpoint 的 `embedding` 路由
- **THEN** 配置的 embedding provider 为 `HttpEmbeddingProvider`,不回落、不告警

#### Scenario: embedding 路由误配仍抛错
- **WHEN** 一个命名 agent 的 `embedding` 路由存在但 target 协议非 `http_embedding`(或缺 endpoint)
- **THEN** `configure_from_active_agent()` 抛 `ModelConfigError`,不静默回落
