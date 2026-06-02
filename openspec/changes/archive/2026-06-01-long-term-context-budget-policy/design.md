## Context

Long-term context 当前已经有可工作的检索和注入链路：

- agent-runtime 在构造 prompt 前调用 `build_context()`。
- long-term-ctx 可以检索 semantic memory 和可选 knowledge-base snippets。
- `BuiltContext.sources` 支持 observability source attribution。
- 已有基础预算控制，但更接近“合并后文本截断”，缺少可解释的来源分配策略。

下一步不是让 LLM 自己决定该注入什么，而是让策略足够稳定：evaluation 和生产排障都能解释某条 memory 或 KB chunk
为什么进入 prompt，或者为什么被裁掉。

## Design

策略把 `available_tokens` 视为 agent-runtime 已经保留 system prompt 和当前对话之后，留给 long-term-ctx 的最大预算。
long-term-ctx 绝不能超过这个值。配置项 `long_term_ctx.max_tokens` 可以进一步降低上限。

在这个总上限内，策略设置来源预算：

- `memory_max_tokens`
- `knowledge_max_tokens`
- `memory_top_k`
- `knowledge_top_k`

这些值是上限，不是配额。memory 没有可用结果时，KB 不需要等待 memory 填满；KB disabled 或无结果时，memory 也可以正常注入。
策略不应该为了填满预算而注入弱相关内容。

选择过程保持确定性：

1. 从 memory 和 knowledge provider 收集候选内容。
2. 使用确定性的 token estimator 估算候选内容成本。
3. 按来源语义优先级、score、可用 recency 和稳定 source id tie-breaker 排序。
4. 在来源预算和总预算允许的范围内注入候选内容。
5. 对未注入候选记录明确原因。

冲突偏好保持保守：

- 事实 / 参考类问题，knowledge 优先于 memory。
- 个人偏好、用户历史、团队背景类问题，memory 优先于 knowledge。
- 如果 query intent 无法判断或存在歧义，维持保守行为：不让弱 memory 挤掉高相关 KB 事实，也不让宽泛 KB 匹配挤掉强相关个人 memory。

MVP 实现可以用一个小的 deterministic query-intent helper，根据显式 query/category 信号和测试样例判断，不引入 LLM。

## Budget Metadata

`BuiltContext` 除了现有 `text` 和 `sources`，还应该暴露预算元数据。具体 dataclass 命名可以在实现阶段确定，但元数据必须能回答：

- effective total budget 是多少。
- memory / knowledge 分别用了多少预算。
- 哪些 source id 被注入，以及估算 token 数。
- 哪些 source id 被排除，以及排除原因。

预期排除原因：

- `zero_available_tokens`
- `provider_disabled`
- `no_results`
- `below_relevance_threshold`
- `source_top_k_exceeded`
- `source_budget_exceeded`
- `total_budget_exceeded`

这些元数据用于 traceability 和测试，不是面向最终用户的解释文本。

## Configuration

初始配置应该保持精简：

- `long_term_ctx.max_tokens`
- `long_term_ctx.memory_max_tokens`
- `long_term_ctx.knowledge_max_tokens`
- `long_term_ctx.memory_top_k`
- `long_term_ctx.knowledge_top_k`
- `long_term_ctx.conflict_preference`

`conflict_preference` 只支持稳定取值，例如 `auto`、`memory`、`knowledge`。默认值为 `auto`。

## Error Handling

Provider 错误保持现有降级语义：KB 不可用时 memory 仍可注入；memory 失败时，KB enabled 且可用时仍可注入。
预算元数据应尽量记录 provider skipped / disabled / failed 状态，但本 change 不应该把可选 provider 失败变成本次请求的硬失败。

## Testing

测试重点是 policy 行为，不是具体 prompt 文案：

- `available_tokens <= 0` 时短路，不发起检索。
- 来源预算分别限制 memory 和 KB。
- 总预算限制合并后的注入内容。
- top-k 限制每个来源的注入条数。
- 事实 / 参考类 query 在冲突时偏向 KB。
- 个人 / 历史类 query 在冲突时偏向 memory。
- 被排除候选会出现在预算元数据中，并带有确定性原因。
- `BuiltContext.sources` 只包含实际注入的来源。

## Non-Goals

本 change 不解决：

- 自动 memory maintenance。
- prompt compression。
- graph retrieval。
- 真实 LLM intent classification。
- 多租户或多 KB 绑定。
- connector-specific ACL 决策。
