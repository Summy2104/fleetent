# agent-cancellation-propagation Specification

## Purpose
TBD - created by archiving change cancellation-propagation. Update Purpose after archive.
## Requirements
### Requirement: 单向 cancel token 通路

平台 SHALL 提供一个 `CancelToken` 取消信号原语，作为单向信号从主循环流入工具调用。`run()` / `run_stream()` MUST 接受一个可选的 cancel token；当未提供时，MUST 使用一个永不取消的默认 token，使现有调用方的可观察行为保持不变。

#### Scenario: 默认 token 永不取消
- **WHEN** 调用方未提供 cancel token
- **THEN** 主循环使用永不取消的默认 token，行为与未引入取消机制时一致

#### Scenario: 取消信号单向传递给工具调用
- **WHEN** 主循环调度一个声明接受 token 的工具
- **THEN** 该 token 作为带外（out-of-band）参数被传入工具执行体，供其在执行中查询

#### Scenario: token 参数不暴露到工具 schema
- **WHEN** 为声明接受 token 的工具构建发送给 LLM 的工具 schema
- **THEN** token 参数被排除在 schema 的 `properties` 与 `required` 之外，LLM 不感知该参数，亦不会被要求为其提供取值

### Requirement: 两层取消保护——cooperative 与硬 deadline

cancel token SHALL 同时支持显式取消与可选的硬 deadline。token 的取消查询 MUST 在「已被显式取消」或「已超过 deadline」任一满足时返回已取消。deadline MUST 基于单调时钟判定，不受系统时钟回拨影响。

#### Scenario: 显式取消即视为已取消
- **WHEN** 外部对 token 调用取消
- **THEN** 此后对该 token 的取消查询返回已取消，且重复取消是幂等的

#### Scenario: 超过 deadline 等同已取消
- **WHEN** token 携带 deadline 且当前单调时间已超过该 deadline
- **THEN** 对该 token 的取消查询返回已取消，无需显式调用取消

#### Scenario: 未到 deadline 且未取消时不视为已取消
- **WHEN** token 携带 deadline 且当前单调时间未到该 deadline，也未被显式取消
- **THEN** 取消查询返回未取消

### Requirement: 主循环在取消时优雅停止

主循环 SHALL 在每个终止检查点查询 cancel token；当 token 已取消时，MUST 以 `cancelled` 原因码停止当次任务，不再发起新的 LLM 调用，并以已产生的内容收尾。接入取消 MUST NOT 修改主循环已有的终止判定分支。

#### Scenario: 取消后停止迭代
- **WHEN** 主循环某轮检查点查询到 token 已取消
- **THEN** 主循环以 `cancelled` 原因终止，返回当前已有回复，不再发起新的 LLM 调用

#### Scenario: 取消以 checker 形式接入
- **WHEN** 主循环构建终止控制器
- **THEN** 取消 checker 被注册并参与每轮终止评估，`max_turns` / `consecutive_failures` / `approval_rejected` 判定不变

### Requirement: 取消时真正中止工具执行并释放资源

当取消到达且某工具正在执行时，接受 token 的工具 SHALL 真正中止其底层资源，而非仅停止等待。对于沙箱代码执行，正在运行的容器 MUST 被强制销毁并释放资源。资源销毁 MUST 幂等，重复销毁不得抛出异常。

#### Scenario: 取消时强制销毁正在运行的沙箱容器
- **WHEN** 沙箱正在执行命令时 token 被取消
- **THEN** 该容器被强制销毁、执行等待被中断、资源被释放，而非等待命令自然结束

#### Scenario: 销毁幂等
- **WHEN** 容器在取消路径已被销毁后，收尾逻辑再次尝试销毁
- **THEN** 二次销毁不抛出异常

### Requirement: 取消终止写入 trace

当任务因取消而停止时，`cancelled` 原因码 SHALL 写入运行日志（trace），并保留取消发生的时点信息。时点信息 MUST 复用 `log_run` 既有的 `ts` / `elapsed_s` 字段（取消在该次运行的相对耗时与时间戳即为可追溯时点），不新增专用 trace 字段。

#### Scenario: 取消终止记录原因码与时点
- **WHEN** 任务因取消被停止
- **THEN** 该次运行的 trace 记录中包含 `cancelled` 原因码，并以既有的 `ts` / `elapsed_s` 字段提供取消发生时点的可追溯信息

### Requirement: cancel token 接口对外契约

cancel token 的接口 SHALL 作为对外契约供后续超时类功能复用。超时类需求 MUST 能通过「构造一个携带 deadline 的 cancel token 并传入工具执行」的方式实现超时，而无需引入并行的另一套取消/超时机制。

#### Scenario: 超时复用 deadline 契约
- **WHEN** 某需求要为工具执行设定超时
- **THEN** 它构造一个 `deadline = 当前单调时间 + 超时时长` 的 cancel token 传入执行体，到点即被取消查询判定为已取消，复用同一中止与资源释放路径

### Requirement: cancelled 终止已接入主循环

取消 checker SHALL 注册进终止框架并使 `cancelled` 成为可触发的终止原因（此前为框架中已定义但无 checker、永不触发的预留原因码）。当主循环检查点查询到 cancel token 已取消时，已注册的取消 checker MUST 以 `cancelled` 原因终止任务，并复用既有 `stop_reason` 出口写入 trace。接入取消 MUST NOT 修改主循环已有的 `max_turns` / `consecutive_failures` / `approval_rejected` 判定分支与优先级。

#### Scenario: cancelled 已接入并可触发
- **WHEN** 主循环检查点查询到 cancel token 已取消
- **THEN** 已注册的取消 checker 以 `cancelled` 原因终止任务

#### Scenario: 接入不改动既有终止判定分支
- **WHEN** 注册取消 checker 后主循环进入每轮终止评估
- **THEN** `max_turns` / `consecutive_failures` / `approval_rejected` 的判定与优先级不变，仅新增 `cancelled` 一路可触发原因

