# sandbox-trace-logging Specification

## Purpose
TBD - created by archiving change sandbox-trace-logging. Update Purpose after archive.
## Requirements
### Requirement: 沙箱执行结果写入 trace

每次沙箱代码执行（`run_code`）完成后 SHALL 向运行日志（trace）追加一条记录，记录中 MUST 包含执行时长、退出码、stdout 字节大小、stderr 字节大小，并带有可区分的类型标记。

#### Scenario: 执行后写入一条沙箱 trace
- **WHEN** `run_code` 完成一次沙箱代码执行
- **THEN** trace 中新增一条带类型标记的记录，含执行时长、退出码、stdout/stderr 字节大小

#### Scenario: 记录携带可选的归属信息
- **WHEN** 执行时已知沙箱 scope 类型与 agent/user 标识
- **THEN** 该记录包含相应的 scope 类型与 agent/user 字段；未知时省略这些字段

### Requirement: trace 记录带统一的类型标记

所有写入运行日志（trace）的记录 MUST 带一个 `kind` 类型标记字段：沙箱执行记 `sandbox_exec`、agent 整轮运行记 `agent_run`、IM 消息记 `im_message`，使消费方可按单一维度区分记录类型。给既有 agent 整轮与 IM 消息记录追加 `kind` MUST 为纯增量——既有字段与写入语义不得改变。

#### Scenario: 沙箱执行记录带 sandbox_exec 标记
- **WHEN** `run_code` 执行后写入 trace
- **THEN** 该记录的 `kind` 为 `sandbox_exec`

#### Scenario: agent 整轮与 IM 消息记录带各自标记
- **WHEN** 写入一条 agent 整轮运行记录或一条 IM 消息记录
- **THEN** 前者 `kind` 为 `agent_run`、后者 `kind` 为 `im_message`，且记录的其余既有字段保持不变

### Requirement: trace 写入路径为单一可隔离常量

运行日志的写入路径 MUST 由单一常量提供，agent 整轮、IM 消息与沙箱执行三类记录共用同一路径常量；该常量 MUST 可被测试注入（monkeypatch），以保证测试隔离不触碰真实数据目录。

#### Scenario: 单一路径覆盖全部 trace 写入
- **WHEN** 测试将 trace 路径常量注入到临时目录
- **THEN** agent 整轮、IM 消息与沙箱执行三类记录的写入都落到该临时目录，没有任何一类绕过隔离写入真实数据目录

### Requirement: trace 仅记录元数据不记录内容

沙箱执行 trace MUST NOT 记录代码原文或完整的 stdout/stderr 内容，仅记录输出的字节大小与执行元数据。

#### Scenario: 不落盘代码与完整输出
- **WHEN** 一次执行产生大量 stdout 输出
- **THEN** trace 记录其字节大小，但不包含 stdout 原文，也不包含被执行的代码原文

### Requirement: trace 写入失败不阻断执行结果返回

trace 写入失败时 MUST NOT 影响 `run_code` 向调用方返回代码执行结果；失败 SHALL 被记录为警告，而非中断主流程或被静默吞掉。

#### Scenario: trace 故障下仍返回执行结果
- **WHEN** 沙箱执行成功但写入 trace 时发生错误
- **THEN** `run_code` 仍正常返回代码执行结果，并记录一条警告日志

#### Scenario: trace 成功不改变返回内容
- **WHEN** 沙箱执行并成功写入 trace
- **THEN** `run_code` 返回给调用方的内容与未引入 trace 时一致

