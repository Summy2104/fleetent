## ADDED Requirements

### Requirement: 沙箱执行结果写入 trace

每次沙箱代码执行（`run_code`）完成后 SHALL 向运行日志（trace）追加一条记录，记录中 MUST 包含执行时长、退出码、stdout 字节大小、stderr 字节大小，并带有可区分的类型标记。

#### Scenario: 执行后写入一条沙箱 trace
- **WHEN** `run_code` 完成一次沙箱代码执行
- **THEN** trace 中新增一条带类型标记的记录，含执行时长、退出码、stdout/stderr 字节大小

#### Scenario: 记录携带可选的归属信息
- **WHEN** 执行时已知沙箱 scope 类型与 agent/user 标识
- **THEN** 该记录包含相应的 scope 类型与 agent/user 字段；未知时省略这些字段

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
