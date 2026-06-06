# session-tool-result-extern Specification

## Purpose
Externalize tool results larger than 50KB to per-session files, keeping session JSON and model context lean.

## Requirements

### Requirement: 大型 tool result 外部化

系统 SHALL 提供 `externalize_tool_results(session_id, messages)` 函数，将 `role=="tool"` 且 content 为超过 50KB（`_TOOL_RESULT_INLINE_LIMIT`）字符串的消息外部化：content 原子写入 `data/sessions/{session_id}.tool_outputs/{tool_call_id}.txt`，消息 content 替换为 `[stored:{tool_call_id}.txt]` 引用。函数 MUST 返回新列表，MUST NOT 修改入参列表。无 tool_call_id 或 content 不超阈值的消息保持内联。

#### Scenario: 超阈值 tool result 外部化
- **WHEN** 一条 tool 消息的 content 超过 50KB，调用 `externalize_tool_results`
- **THEN** content 写入 `{session_id}.tool_outputs/{tool_call_id}.txt`，返回列表中该消息 content 为 `[stored:{tool_call_id}.txt]`

#### Scenario: 小于阈值的 tool result 保持内联
- **WHEN** 一条 tool 消息的 content 小于 50KB
- **THEN** 该消息 content 不变，不创建外部文件

#### Scenario: 非 tool 消息不外部化
- **WHEN** 一条 user 或 assistant 消息的 content 超过 50KB
- **THEN** 该消息不被外部化，content 保持原样

#### Scenario: 不修改入参列表
- **WHEN** 调用 `externalize_tool_results(session_id, messages)`
- **THEN** 原 messages 列表内容不被修改，返回的是新列表

### Requirement: tool result 引用读回

系统 SHALL 提供 `rehydrate_tool_results(session_id, messages)` 函数，将 content 为 `[stored:xxx.txt]` 引用的消息读回完整 content。外部文件缺失时 MUST 保留引用占位（不报错）。返回新列表，不修改入参。

#### Scenario: 读回外部化内容
- **WHEN** 对含 `[stored:abc.txt]` 引用的消息调用 `rehydrate_tool_results`，且外部文件存在
- **THEN** 该消息 content 被替换回外部文件的完整内容

#### Scenario: 外部文件缺失保留引用
- **WHEN** 引用对应的外部文件不存在
- **THEN** 该消息 content 保持 `[stored:xxx.txt]` 引用占位，不抛出异常

#### Scenario: 无引用消息原样返回
- **WHEN** 消息列表中无任何 `[stored:...]` 引用
- **THEN** 返回的列表内容与输入一致
