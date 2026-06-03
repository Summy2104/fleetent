# model-parameter-config Specification

## Purpose
TBD - created by archiving change model-parameter-config. Update Purpose after archive.
## Requirements
### Requirement: task_type 级默认采样参数

`RouteConfig` SHALL 提供一个采样参数容器 `params`，承载该 `task_type` 的默认采样参数（如 `temperature` / `top_p`）。未配置任何采样参数时，`params` MUST 为空，且对应 `task_type` 的 LLM 调用行为 MUST 与现状逐字节一致（不向 provider 传任何采样参数，由 provider 取默认）。

#### Scenario: 未配置采样参数时保持现状
- **WHEN** 某 `task_type` 的路由配置未设置任何采样参数
- **THEN** 该 `task_type` 的 LLM 调用不传任何采样参数，行为与现状一致，采样由 provider 默认决定

#### Scenario: 配置的 task_type 采样参数透传给底层调用
- **WHEN** 某 `task_type` 的路由配置设置了采样参数（如 `temperature`）
- **THEN** 该 `task_type` 的每次 LLM 调用均把这些采样参数透传给底层 `create()`，与一等字段 `max_tokens` 并列且互不影响

### Requirement: 单次调用采样参数覆盖与深合并

单次调用 SHALL 能通过覆盖意图（`RouteOverride.params`）覆盖采样参数。最终生效的采样参数 MUST 为 task_type 默认参数与调用覆盖参数的深合并：覆盖意图中出现的键 MUST 替换 task_type 默认中的同名键，未被覆盖的 task_type 默认键 MUST 沿用。优先级为**调用覆盖 > task_type 默认 > provider 默认**。`max_tokens` MUST 保持独立的一等字段，不并入采样参数容器。

#### Scenario: 调用覆盖按键深合并
- **WHEN** 某 task_type 默认采样参数为 `{"temperature": 0.7, "top_p": 0.9}`，调用覆盖仅设置 `{"temperature": 0.0}`
- **THEN** 最终生效的采样参数为 `{"temperature": 0.0, "top_p": 0.9}`——`temperature` 取覆盖值、`top_p` 沿用 task_type 默认

#### Scenario: 覆盖新增键且 max_tokens 不并入采样参数
- **WHEN** 调用覆盖新增一个 task_type 默认中不存在的采样键
- **THEN** 最终生效的采样参数包含该新增键并保留 task_type 默认的其余键，而 `max_tokens` 仍作为独立一等字段单独传给底层调用，不出现在采样参数容器中

