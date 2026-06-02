## Why

常乐负责的 intelligence / observability / deployment-config 相关模块已经有较高的综合测试覆盖率，
但覆盖主要由 integration 和 evaluation tests 承担。当前相关模块的单元测试覆盖率约为 64%，而综合
覆盖率约为 93%。这说明核心行为已经被验证，但不少纯逻辑、provider payload / error parsing 和失败
分支只能通过较重的测试间接覆盖。

这个 change 用于补齐轻量单元测试，提升日常开发反馈速度和边界回归质量。目标不是追求覆盖率数字本身，
而是把最适合单元测试的逻辑移到 unit 层稳定覆盖。

## What Changes

- 为常乐负责模块建立单元测试加固目标：相关 unit coverage 从当前约 64% 提升到至少 75%。
- 优先补齐纯逻辑和边界逻辑：
  - `observability.performance` / `observability.usage` 的聚合、容错和排序。
  - `vector_store.embeddings` / `vector_store.rerank` 的 HTTP provider payload、错误解析和禁止隐式 fallback。
  - `reflection` 的 finding / maintenance proposal 过滤、风险判断和 payload redaction。
  - `memory_layer` 的 invalid action、跨用户保护、TTL / stale 规则。
  - Google Drive / Confluence connector 的认证、429、unsupported payload 和失败分支。
- 保持 DB / runtime 编排行为继续由 integration tests 验证，不把 integration tests 强行改写成 mock-heavy unit tests。
- 更新 roadmap，把该 change 记录为 MVP foundation 之后的质量加固项。

## Out of Scope

- 不改生产行为。
- 不重构 public API。
- 不新增 coverage CI gate。
- 不要求单元测试覆盖率达到 90%+。
- 不把 `knowledge_base.store`、`knowledge_base.runtime`、trace SQLite 写入等强 DB / runtime 编排路径硬拆成单元测试。
- 不删除或降级已有 integration / evaluation tests。

## Module Boundary Impact

- **Owning package**: `ci-quality-gate` / test suite；测试覆盖对象属于 `intelligence`、`observability`、`memory_layer`、`config` 和 `scripts.upgrade`。
- **Public API surface**: 无新增生产 public API。
- **Owned tables**: 无。
- **Config namespace**: 无。
- **Cross-module dependencies**: 无新增 runtime dependency；只新增测试对 existing public API 或可注入 helper 的覆盖。
- **Migration / shim plan**: 无。
