# agent-cost-budget Specification

## Purpose
五层 turns/tokens 用量分层预算（task/session/user/agent/global）。注：原 AR18 设计含 `cost_usd` 成本维度，经 zy 评审（2026-06-02）认定成本统计无实际意义而整体移除；本能力仅保留 turns/tokens 用量治理，成本相关需求（含 `headroom()` / `BudgetHeadroom` 与成本感知路由 MR2）一并撤销。
## Requirements
### Requirement: 系统内部操作豁免计入预算

系统内部 LLM 操作（上下文压缩、Grace Call 自身）MUST NOT 计入任何层级的预算累计。豁免 SHALL 沿用 AR2 契约——仅主循环推进用户任务的 LLM 调用进入累计入口，内部调用不接入该入口即豁免，不需额外豁免开关。

#### Scenario: 压缩调用不计入累计
- **WHEN** 一次运行中触发了上下文压缩
- **THEN** 压缩消耗的 token 不计入任何层级的累计用量

