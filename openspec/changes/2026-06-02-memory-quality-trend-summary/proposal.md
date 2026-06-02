# memory-quality-trend-summary

## Why

memory 已有 extraction evaluation、retention/compaction、owner-approved maintenance proposals 和 Shared Memory
数据层。当前仍缺一层质量趋势视图，用来判断 memory extraction 是否变好、proposal apply 是否减少重复 /
冲突、retention 是否稳定控制容量。

上游实现已经足够稳定，可以进入设计。第一版应只做只读趋势汇总，不自动修改 memory，不触发 extraction。

## What Changes

- 新增 Memory Quality Trend summary public API。
- 聚合 User Memory 数量、type 分布、expired context、duplicate candidates、maintenance proposal 状态、
  extraction evaluation 结果和 Shared Memory 数量趋势。
- 支持 deterministic evaluation fixture。
- 输出用于 owner / operator 评估，不驱动自动写回。

## Out Of Scope

- 不实现 scheduler、UI、告警或自动 cleanup。
- 不运行真实 LLM evaluation。
- 不自动创建 reflection proposal。
- 不修改 User Memory 或 Shared Memory。

## Module Boundary Impact

- owning package：`fleetent.intelligence.memory`
- public API surface：`MemoryQualityTrendQuery`、`MemoryQualityTrendSummary`、`get_memory_quality_trend_summary()`
- owned tables：无新增表；读取 `memory_items`、`shared_memory_items` 和 reflection-owned proposal records（通过 reflection public/read boundary）
- config namespace：无新增配置
- cross-module dependencies：只读依赖 reflection proposal lifecycle API；不 import reflection internal helpers
- migration / shim plan：无迁移
