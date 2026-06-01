# agent-loop-detection Specification

## Purpose
TBD - created by archiving change loop-detection. Update Purpose after archive.
## Requirements
### Requirement: 粗粒度循环检测注册进终止框架

循环检测 SHALL 实现为一个独立的终止 checker 并注册到 `TerminationController`，复用终止框架预留的 `loop_detected` 原因码。接入循环检测 MUST NOT 修改主循环已有的终止判定分支（`max_turns` / `consecutive_failures` / `approval_rejected`）。

#### Scenario: 循环检测以 checker 形式接入
- **WHEN** 主循环构建终止控制器
- **THEN** 循环检测 checker 被注册，并在每轮终止评估中被调用，主循环已有判定分支不变

#### Scenario: 无重复调用时不干预
- **WHEN** 主循环各轮的工具调用各不相同（工具名或参数指纹不同）
- **THEN** 循环检测 checker 不命中，循环行为与现状一致

### Requirement: 同一工具无进展的反复调用识别为循环

循环检测 SHALL 基于两个互补信号识别「反复调用同一工具却毫无进展」，任一信号在近期工具调用历史中达到配置阈值即判定为一次循环命中：(A) 同一工具名 + 归一化参数指纹重复；(B) 同一工具名的**成功**调用产出**相同结果摘要**，不论参数是否变化。语义相同但键序不同的参数 MUST 归一化为同一指纹。失败结果 MUST NOT 计入信号 B（连续失败由既有 `consecutive_failures` 终止覆盖，避免双重计数）。参数与结果均不同的调用 MUST NOT 计入任一重复。

#### Scenario: 相同工具相同参数累计重复（信号 A）
- **WHEN** 同一工具以实质相同的参数被反复调用并达到配置的重复阈值
- **THEN** 循环检测判定为一次循环命中

#### Scenario: 参数键序不同不影响指纹
- **WHEN** 同一工具两次调用的参数语义相同、仅 JSON 键顺序不同
- **THEN** 两次调用得到同一参数指纹，计入同一重复

#### Scenario: 参数含易变字段但结果不变识别为循环（信号 B）
- **WHEN** 同一工具被反复调用、参数因含时间戳 / 随机 id 等易变字段而每次不同，但每次成功返回的结果摘要相同并达到阈值
- **THEN** 循环检测经信号 B 判定为一次循环命中，不因参数指纹每次不同而漏判

#### Scenario: 结果每次不同不计入信号 B
- **WHEN** 同一工具被多次调用且每次成功返回的结果实质不同（结果摘要不同）
- **THEN** 信号 B 不累计为循环重复，正常放行（不误杀正在推进的工具）

#### Scenario: 参数与结果均不同不计入重复
- **WHEN** 同一工具被多次调用但每次参数实质不同、结果也不同
- **THEN** 信号 A 与信号 B 均不命中，不累计为循环重复

### Requirement: 两段式响应——先注入警告再强制终止

首次检测到循环时，循环检测 SHALL 触发向消息序列注入一条警告提示（提示 AI 正在重复且无进展），且此轮 MUST NOT 终止任务。注入警告后若同一循环模式再次达到阈值，循环检测 MUST 以 `loop_detected` 原因码终止当次任务。注入警告 MUST NOT 发起额外的 LLM 调用。

#### Scenario: 首次命中注入警告不终止
- **WHEN** 循环检测首次达到重复阈值且尚未注入过警告
- **THEN** 向消息序列追加一条警告提示，任务继续进入下一轮，不终止

#### Scenario: AI 忽略警告仍重复则强制终止
- **WHEN** 警告已注入后同一循环模式再次达到重复阈值
- **THEN** 主循环以 `loop_detected` 原因终止，返回当前已有回复，不再发起新的 LLM 调用

#### Scenario: 警告注入不触发额外 LLM 调用
- **WHEN** 循环检测请求注入警告
- **THEN** 警告作为普通消息追加进上下文，在下一轮正常 LLM 调用时送达，期间不发起额外的 LLM 请求

### Requirement: 检测阈值可配置且终止写入 trace

循环检测的重复阈值 SHALL 可通过参数注入或配置覆盖默认值。当任务因 `loop_detected` 终止时，该原因码 MUST 写入运行日志（trace）。

#### Scenario: 阈值可注入
- **WHEN** 以较小的重复阈值注入循环检测
- **THEN** 达到该较小阈值即触发对应的两段式响应

#### Scenario: 循环终止记录原因码
- **WHEN** 任务因检测到循环被强制终止
- **THEN** 该次运行的 trace 记录中包含 `loop_detected` 原因码

### Requirement: 警告注入对压缩轮的可见性

当注入循环警告的那一轮恰好触发上下文压缩时，循环检测 SHALL 保证警告内容不被压缩摘要静默吞掉而对 AI 不可见。警告消息 MUST 以 AI 在下一轮 LLM 调用中能实际读到的形式存在于发送给 LLM 的消息序列中。

#### Scenario: 警告与压缩同轮发生时仍对 AI 可见
- **WHEN** 注入循环警告的那一轮同时满足压缩触发条件
- **THEN** 警告内容以 AI 下一轮可读的形式保留在送往 LLM 的消息序列中，不被压缩摘要吞掉

### Requirement: loop_detected 终止已接入主循环

循环检测 checker SHALL 注册进终止框架并使 `loop_detected` 成为可触发的终止原因（此前为框架中已定义但无 checker、永不触发的预留原因码）。当主循环检测到「同一工具反复调用却无进展」且 AI 忽略警告仍重复时，已注册的循环检测 checker MUST 以 `loop_detected` 原因终止任务，并复用既有 `stop_reason` 出口写入 trace。接入循环检测 MUST NOT 修改主循环已有的 `max_turns` / `consecutive_failures` / `approval_rejected` 判定分支与优先级。

#### Scenario: loop_detected 已接入并可触发
- **WHEN** 主循环检测到「同一工具反复调用却无进展」且 AI 忽略警告仍重复
- **THEN** 已注册的循环检测 checker 以 `loop_detected` 原因终止任务

#### Scenario: 接入不改动既有终止判定分支
- **WHEN** 注册循环检测 checker 后主循环进入每轮终止评估
- **THEN** `max_turns` / `consecutive_failures` / `approval_rejected` 的判定与优先级不变，仅新增 `loop_detected` 一路可触发原因

