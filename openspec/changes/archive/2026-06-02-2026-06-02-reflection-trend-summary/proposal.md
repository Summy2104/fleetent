# reflection-trend-summary

## Why

reflection 已经能生成三类稳定输入：基础 `ReflectionReport`、只读 `KnowledgeBaseReflectionReport`，
以及 User Memory / Skill proposal lifecycle。当前缺口是这些信号只能逐次查看，无法回答“过去一段时间
哪些 finding 类型在增加、哪些 proposal 被采纳、memory / KB / skill 改进是否有效”。

本 change 只设计趋势汇总能力，不实现代码。上游边界已经足够稳定：reflection reports 与 KB reflection
reports 都持久化且脱敏，memory / skill proposal 有状态生命周期，observability 可按时间查询 trace。

## What Changes

- 新增 reflection-owned trend summary public API，用于按 scope、时间窗口和 finding domain 聚合趋势。
- 汇总输入仅来自 reflection public/store 边界：`reflection_reports`、`kb_reflection_reports`、
  `memory_maintenance_proposals`、`skill_proposals`。
- 输出按 finding type、severity/risk、proposal status、applied/rejected ratio 和 week/day bucket 聚合。
- 支持 deterministic evaluation fixture，验证趋势方向、状态计数和 transcript redaction。
- 不自动创建 proposal，不自动写 Memory / KB / Skill。

## Out Of Scope

- 不实现 UI、scheduler、告警或自动优化策略。
- 不读取完整 transcript，不做 LLM summary。
- 不把 trend 结果反向写入 reflection findings。
- 不改变 existing report/proposal lifecycle。

## Module Boundary Impact

- owning package：`fleetent.intelligence.reflection`
- public API surface：`ReflectionTrendSummary`、`ReflectionTrendBucket`、`get_reflection_trend_summary(query)`
- owned tables：无新增表；读取 reflection-owned reports/proposals 表
- config namespace：无新增配置
- cross-module dependencies：只读使用 reflection 自有持久化；不依赖 memory / KB / skill internal 实现
- migration / shim plan：无迁移
