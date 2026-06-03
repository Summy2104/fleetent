# tool-parallel-dispatch Specification

## Purpose
TBD - created by archiving change tool-parallel-dispatch. Update Purpose after archive.
## Requirements
### Requirement: 同一轮多工具并行调度

当 LLM 一轮返回多个 `tool_calls` 时，主循环 SHALL 并发执行本轮待执行的工具调用，而非顺序逐个执行。并发执行 MUST 仅作用于工具执行（dispatch）阶段；guardrail 判定与风险审批 MUST 保持按原 `tool_calls` 顺序串行决策。单个 `tool_call`（N=1）时，行为 MUST 与未引入并行机制时一致。

#### Scenario: 多个独立工具并行执行
- **WHEN** LLM 一轮返回多个无短路、无待审批阻断的 `tool_calls`
- **THEN** 这些工具的执行被并发调度，而非顺序逐个等待，本轮工具总耗时不再线性叠加

#### Scenario: 单工具调用与现状等价
- **WHEN** LLM 一轮仅返回一个 `tool_call`
- **THEN** 其消息回填、流式事件顺序与失败计数与未引入并行机制时一致

#### Scenario: 决策阶段保持串行
- **WHEN** 主循环处理一轮多个 `tool_calls`
- **THEN** 每个工具的 guardrail 判定与（medium/high）风险审批按原 `tool_calls` 顺序串行进行，仅工具执行被并发

### Requirement: 结果按原序回填且 tool-pair 合法

并行执行的工具结果 SHALL 按**原 `tool_calls` 顺序**回填进消息列表。每个 assistant（含 N 个 `tool_calls`）消息之后 MUST 紧跟 N 条 `role:"tool"` 结果消息，每条以对应的 `tool_call_id` 配对，且顺序等于原 `tool_calls` 顺序。回填结果 MUST 不破坏消息卫生（sanitize）对 assistant→tool 配对完整性的校验。

#### Scenario: 回填顺序等于原 tool_calls 顺序
- **WHEN** 一批工具并发完成（完成先后可能与原顺序不同）
- **THEN** tool 结果消息按原 `tool_calls` 索引顺序回填，不按完成先后回填

#### Scenario: 每个 tool_call 配对一条 tool 结果
- **WHEN** assistant 消息含 N 个 `tool_calls`
- **THEN** 其后紧跟恰好 N 条 tool 结果消息，每条 `tool_call_id` 与对应 `tool_call` 一一匹配，消息卫生校验不触发修复

### Requirement: 并行批次取消传播

并行批次内的所有工具 SHALL 共享同一 run-level cancel token。当取消或 deadline 命中时，批次内所有在途工具 MUST 被真正中止（如沙箱代码执行被强制销毁容器并释放资源），而非等待其自然结束。取消收尾时，消息序列 MUST 保持合法——每个 `tool_call` MUST 仍有一条对应的 tool 结果消息（已完成的填其结果，被取消 / 超时的填归一化的失败占位），不得遗留半截 tool-pair。

#### Scenario: 取消中止全批在途工具
- **WHEN** 一批工具并行执行期间 cancel token 被取消或 deadline 命中
- **THEN** 批次内所有在途工具被中止并释放资源，主循环在下一检查点以 `cancelled` 终止

#### Scenario: 取消后消息序列仍合法
- **WHEN** 取消发生时批次内部分工具已完成、部分在途
- **THEN** 每个 `tool_call` 都被回填一条 tool 结果消息（完成结果或失败占位），不遗留无配对的 `tool_call`

### Requirement: 多风险工具审批策略——审批串行、执行并行

当一轮内含多个 medium/high 风险工具时，平台 SHALL 按原 `tool_calls` 顺序**逐个**请求审批，每个等待其决策后再处理下一个。被拒的工具 MUST 不进入并行执行批，并沿用既有的拒批占位结果与终止标记。只有全部审批完成且被批准的工具 MUST 才进入并行执行批。平台 MUST NOT 同时并发触发多个审批请求。

#### Scenario: 多高危工具审批逐个进行
- **WHEN** 一轮含多个 medium/high 风险工具
- **THEN** 审批按原 `tool_calls` 顺序串行逐个请求，不并发推送多个审批

#### Scenario: 全部批准后才并行执行
- **WHEN** 多个高危工具全部审批通过
- **THEN** 这些工具进入同一并行批执行

#### Scenario: 被拒工具不进并行批
- **WHEN** 某高危工具审批被拒
- **THEN** 该工具不被执行，回填拒批占位结果并置终止标记，其余被批准工具仍并行执行

### Requirement: 单工具失败隔离与逐结果计数

并行批次内单个工具的失败（执行崩溃或超时，归一化为失败）SHALL 不影响同批其余工具的执行。连续失败计数（`consecutive_failures`）与循环检测窗口记录 MUST 按原 `tool_calls` 顺序**逐结果**更新，语义与顺序执行等价——一个成功结果清零、一个失败结果加一，按原序逐个套用；MUST NOT 采用批级聚合计数（如「全部失败才加一」）。

#### Scenario: 单工具失败不影响同批其余
- **WHEN** 并行批中某工具执行失败而其余成功
- **THEN** 失败被归一化为该工具的失败结果，其余工具正常返回结果，整批不因单失败中断

#### Scenario: consecutive_failures 逐结果更新
- **WHEN** 一批工具完成后按原序回填
- **THEN** `consecutive_failures` 按原 `tool_calls` 顺序逐结果更新（成功清零、失败加一），与顺序执行同等结果

### Requirement: 单轮并发上限可配置

单轮工具并行度 SHALL 受一个可配置上限约束（经 Settings 提供默认值，可经 `.env` / 配置文件覆盖、可注入）。当待执行工具数超过上限时，平台 MUST 分批执行（批间串行），所有批完成后按原序统一回填，分批 MUST NOT 改变最终回填顺序。当上限配置为 1 或更小时，行为 MUST 退化为全顺序执行。

#### Scenario: 超过上限时分批
- **WHEN** 一轮待执行工具数超过配置的并发上限
- **THEN** 工具分批并发执行（批间串行），最终回填仍严格按原 `tool_calls` 顺序

#### Scenario: 上限为 1 退化为顺序
- **WHEN** 并发上限配置为 1 或更小
- **THEN** 工具按原顺序逐个执行，等价未引入并行机制

### Requirement: 共享沙箱容器并发边界

对共享同一会话沙箱容器的有状态工具（如沙箱代码执行），平台 SHALL 在并行批内按其共享资源键串行化执行，以避免对同一容器并发执行造成状态干扰；不共享状态的工具不受此约束，仍并行执行。

#### Scenario: 同容器代码执行串行化
- **WHEN** 一轮内含多个作用于同一会话沙箱容器的代码执行工具调用
- **THEN** 它们对该容器按资源键串行执行，不对同一容器并发执行

#### Scenario: 无共享状态工具仍并行
- **WHEN** 一轮内含多个无共享容器状态的工具（如查询 / 抓取类）
- **THEN** 这些工具正常并行执行，不受沙箱串行化约束

### Requirement: 流式并行期事件按原序

在流式（`run_stream`）路径下，并行执行期的 `tool_call` 与 `tool_result` 事件 SHALL 按原 `tool_calls` 顺序产出。`tool_result` 事件 MUST 在全批执行完成后按原序逐个产出，而非按完成先后产出。每个 `tool_call` MUST 对应产出一个 `tool_result` 事件（取消 / 失败时为占位内容），不得泄漏半截事件。

#### Scenario: tool_result 按原序产出
- **WHEN** 流式路径下一批工具并发完成（完成先后不一）
- **THEN** `tool_result` 事件按原 `tool_calls` 顺序逐个产出，不按完成先后产出

#### Scenario: 每个 tool_call 对应一个 tool_result 事件
- **WHEN** 流式路径下一轮含 N 个 `tool_calls`（含取消或失败的）
- **THEN** 恰好产出 N 个 `tool_result` 事件，与 N 个 `tool_call` 事件一一对应，不泄漏半截事件

