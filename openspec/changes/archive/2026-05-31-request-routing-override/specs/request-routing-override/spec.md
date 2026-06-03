## ADDED Requirements

### Requirement: 请求级路由覆盖入口

`get_async_client_and_config` 与 `get_client_and_config` SHALL 接受一个可选的覆盖意图（`RouteOverride`）。当未提供覆盖意图时，两函数 MUST 与现状一致，仅按 `task_type` 查 `ROUTES` 返回路由结果，行为不变。

#### Scenario: 不传覆盖时保持现状
- **WHEN** 调用 `get_async_client_and_config("default")` 且不传覆盖意图
- **THEN** 返回的配置与 `task_type` 路由结果完全一致，模型、base_url、fallbacks 均不变

#### Scenario: 提供覆盖意图时按字段生效
- **WHEN** 调用时传入仅设置了 `model` 的覆盖意图
- **THEN** 返回配置的模型为覆盖值，其余字段沿用该 `task_type` 的路由结果

### Requirement: 字段级覆盖语义

覆盖意图 SHALL 按字段 merge 到 task_type 路由结果：覆盖意图中非 None 的字段 MUST 替换对应字段，为 None 的字段 MUST 沿用 task_type 路由结果。

#### Scenario: 仅覆盖模型其余沿用
- **WHEN** 覆盖意图只设置 `model="claude-haiku-4-5"`，其余字段为 None
- **THEN** 最终配置模型为 `claude-haiku-4-5`，base_url 与 api_key_env 沿用原 task_type 路由结果

#### Scenario: 覆盖多个字段
- **WHEN** 覆盖意图同时设置 `model` 与 `base_url`
- **THEN** 最终配置的模型与 base_url 均为覆盖值，未设置的字段沿用 task_type 路由结果

### Requirement: 覆盖模型默认清空 fallback 链

当覆盖意图设置了 `model` 且未显式提供 `fallbacks` 时，最终配置的 fallback 链 MUST 为空——请求级覆盖语义为「本次就用该模型」，不得回落到原 task_type 的 fallback。调用方若显式提供 `fallbacks` 覆盖值，则以该值为准。

#### Scenario: 覆盖模型时不保留原 fallback
- **WHEN** 原 task_type 路由结果含非空 fallbacks，覆盖意图设置了 `model` 但未提供 `fallbacks`
- **THEN** 最终配置的 fallbacks 为空，主循环仅尝试覆盖后的单一模型

#### Scenario: 显式提供 fallbacks 覆盖
- **WHEN** 覆盖意图同时设置了 `model` 与非空 `fallbacks`
- **THEN** 最终配置的 fallbacks 为覆盖提供的值

### Requirement: agent_loop 暴露 force_model 透传

`run()` 与 `run_stream()` SHALL 暴露可选参数 `force_model`。当为 None 时 MUST 与现状一致；当为非 None 时 MUST 组装为覆盖意图透传给路由层，使本次任务的全部 LLM 调用使用该模型。

#### Scenario: force_model 为 None 不改变行为
- **WHEN** 调用 `run()` 不传 `force_model`
- **THEN** 路由层不接收覆盖意图，task_type 路由与 fallback 链行为与现状一致

#### Scenario: force_model 指定模型贯穿本次任务
- **WHEN** 调用 `run()` 传入 `force_model="claude-haiku-4-5"`
- **THEN** 本次任务每轮 LLM 调用均使用 `claude-haiku-4-5`，不回落到 task_type 默认模型

### Requirement: 覆盖后的实际模型写入 trace

任务结束时，运行日志（trace）记录的模型 MUST 为本次实际使用的模型——发生覆盖时记录覆盖后的模型，未覆盖时记录 task_type 默认模型。

#### Scenario: 覆盖时 trace 记录覆盖模型
- **WHEN** 以 `force_model="claude-haiku-4-5"` 运行任务并正常结束
- **THEN** 该次运行的 trace 记录的模型为 `claude-haiku-4-5`

#### Scenario: 未覆盖时 trace 记录默认模型
- **WHEN** 不传 `force_model` 运行任务
- **THEN** trace 记录的模型为 task_type 路由结果的模型
