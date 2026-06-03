# message-hygiene Specification

## Purpose
TBD - created by archiving change message-hygiene. Update Purpose after archive.
## Requirements
### Requirement: 发送前消息契约校验与修复

消息卫生层 SHALL 提供 `sanitize()`，在每轮 LLM 调用前对消息序列做契约校验与自动修复，返回一个保证合法的新序列与一份修复报告。`sanitize()` MUST NOT 修改传入的原始消息列表。主循环（`run()` / `run_stream()`）MUST 在 `maybe_compress` 之后、发起 LLM 调用之前调用 `sanitize()`，并以其返回的合法序列发给 LLM。

#### Scenario: 合法序列原样通过
- **WHEN** 传入一个已满足契约的消息序列
- **THEN** `sanitize()` 返回内容等价的序列，报告标记未发生修复，主循环正常调用 LLM

#### Scenario: 修复后的序列才发给 LLM
- **WHEN** 传入一个含契约违规的消息序列
- **THEN** 主循环以 `sanitize()` 修复后的合法序列发起 LLM 调用，而非原始非法序列

### Requirement: 修复连续同角色消息

当消息序列中出现相邻两条同角色消息时，卫生层 MUST 通过合并内容或插入占位消息使角色序列合法，且 MUST NOT 破坏既有的工具调用与结果配对。

#### Scenario: 相邻同角色文本消息被合并
- **WHEN** 序列中存在两条相邻的同角色文本消息
- **THEN** 修复后这两条被合并或被占位消息隔开，序列不再出现相邻同角色违规

### Requirement: 补全缺失的 tool_result

当某 assistant 消息含 `tool_call` 但序列中找不到对应 `tool_call_id` 的 tool_result 时，卫生层 MUST 补一条「工具执行失败」占位 tool_result，使每个 tool_call 都有对应 result。

#### Scenario: 缺失的 tool_result 被占位补全
- **WHEN** 序列中有一个 tool_call 没有对应的 tool_result
- **THEN** 修复后该 tool_call 拥有一条占位的「工具执行失败」tool_result，序列对 LLM 合法

### Requirement: 移除孤立的 tool_result

当某 tool_result 的 `tool_call_id` 在序列中找不到对应的 assistant `tool_call` 时，卫生层 MUST 移除该孤立 tool_result。

#### Scenario: 孤立的 tool_result 被移除
- **WHEN** 序列中存在一条 `tool_call_id` 无对应 tool_call 的孤立 tool_result
- **THEN** 修复后该孤立 tool_result 被移除，序列不再含未配对的 tool_result

### Requirement: 修复动作写入 trace

当卫生层发生任何修复时，修复动作（修复类型与数量）SHALL 写入运行日志（trace）。未发生修复的运行 MUST NOT 写入该字段。

#### Scenario: 发生修复时记录修复动作
- **WHEN** `sanitize()` 对序列执行了一项或多项修复
- **THEN** 该次运行的 trace 记录中包含修复类型与数量

#### Scenario: 未修复时不记录
- **WHEN** 序列已合法、`sanitize()` 未做任何修复
- **THEN** trace 记录中不包含修复动作字段

### Requirement: 无法安全修复时尽早报错

当校验出本层规则无法安全修复的违规时，卫生层 MUST 在发起 LLM 调用之前抛出明确错误，而非将非法序列传给 LLM。

#### Scenario: 不可修复的违规阻止 LLM 调用
- **WHEN** 传入一个结构性损坏、无法被卫生规则安全修复的消息序列
- **THEN** `sanitize()` 抛出明确错误，主循环不发起该轮 LLM 调用

