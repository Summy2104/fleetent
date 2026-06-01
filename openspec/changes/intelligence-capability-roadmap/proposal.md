## Why

常乐负责的模块已经包含 observability、memory、long-term context、reflection、vector store、
knowledge base、evaluation 和 deployment/config 的一部分。继续逐个讨论 spec 会导致两个问题：

- 很难判断“做完当前 spec 后整体离 MVP 还有多远”。
- 后续 specs 的依赖关系、并行边界和 stop condition 容易靠会话记忆维护。

需要一份文档型 roadmap，把这些能力域放在同一张图里管理，作为后续 OpenSpec 的入口。

## What Changes

- 新增 `docs/capabilities/intelligence-roadmap.md`。
- 定义常乐负责能力域的状态、MVP 缺口、非 MVP 增强和依赖关系。
- 将后续 specs 分成 M1-M4 实施批次。
- 明确哪些 specs 可以并行、哪些不应提前做。
- 定义常乐负责模块的 MVP-ready 判定标准。

## Out of Scope

- 不改代码。
- 不调整现有模块实现。
- 不为每个候选 spec 写详细 proposal。
- 不替代单个 capability 文档；roadmap 只做跨能力总控。

## Module Boundary Impact

- **Owning package**: none，文档型 change。
- **Public API surface**: none。
- **Owned tables**: none。
- **Config namespace**: none。
- **Cross-module dependencies**: documents relationships across observability、intelligence、deployment。
- **Migration / shim plan**: none。
