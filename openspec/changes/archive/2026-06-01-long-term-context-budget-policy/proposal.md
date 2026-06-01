## Why

`long-term-context-foundation` 已经恢复 memory 和可选 knowledge-base 的长期上下文注入链路，但当前预算策略仍然偏粗：
基本是 memory 优先，合并文本超预算时截断低优先级内容。这可以作为地基，但还没有清楚定义当前对话、memory 和 KB
在有限 prompt 空间里如何竞争。

随着 memory 和 KB 检索能力增强，不受控的上下文注入反而可能让回答变差：过期 memory 可能覆盖用户当前意图，宽泛 KB
匹配可能挤占个人上下文，工程师也很难解释某个来源为什么被注入或被裁掉。

本 change 引入确定性的长期上下文预算策略，让上下文选择保持保守、可测试、可观测。

## What Changes

- 增加确定性的 long-term context budget policy，分别约束 memory 和 knowledge 的来源预算。
- 当前对话优先级仍由 agent-runtime 保证；`available_tokens` 继续表示 agent-runtime 在保留 system prompt 和当前对话后，
  传给 long-term-ctx 的硬上限。
- 按来源语义选择 memory 和 KB snippet：
  - memory 适合用户偏好、长期背景、历史承诺、个人 / 团队上下文。
  - knowledge 适合事实、流程、制度、项目资料和企业参考文档。
  - 来源冲突时，事实 / 参考类问题默认 KB 胜出；个人偏好 / 历史上下文类问题默认 memory 胜出。
- 使用 token 估算、来源最大预算、top-k、相关度、可用 recency 和稳定 tie-breaker 做确定性裁剪。
- 在 `BuiltContext` 中返回预算决策元数据，便于 observability 记录被注入、被裁剪、被跳过的来源。
- 增加少量 `long_term_ctx.*` 配置：总上下文预算、memory 预算、knowledge 预算、各来源 top-k、冲突偏好。
- 更新 long-term context 文档和 roadmap 状态。

## Out of Scope

- 不做 LLM 驱动的上下文选择、总结、改写或压缩。
- 不做自动 memory 写入、删除、合并、压缩或 reflection maintenance action。
- 不做 graph search、多 KB 绑定、tenant-aware ACL policy 或 connector-specific retrieval policy。
- 不做 prompt template 产品化；除最小预算配置外，不做 per-agent 自定义模板。
- 不新增持久化表。
- 不做 HTTP endpoint、admin UI、dashboard 或后台 job。

## Module Boundary Impact

- **Owning package**：`intelligence.long_term_ctx`。
- **Public API surface**：新增预算策略相关 dataclass，以及 `BuiltContext` 的预算元数据。现有
  `build_context(user_id, query, agent_id, available_tokens)` 仍是主要 public API。
- **Owned tables**：无。
- **Config namespace**：`long_term_ctx.*`。
- **Cross-module dependencies**：通过现有 public provider contract 读取 memory 和 knowledge；observability 可以通过现有
  source attribution / runtime event 流程消费返回的预算元数据。
- **Migration / shim plan**：无；增量 API。现有只读取 `BuiltContext.text` 和 `BuiltContext.sources` 的调用方继续可用。
