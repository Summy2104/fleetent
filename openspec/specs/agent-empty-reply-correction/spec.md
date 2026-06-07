# agent-empty-reply-correction Specification

## Purpose
TBD - created by archiving change agent-empty-reply-correction. Update Purpose after archive.
## Requirements
### Requirement: 空最终回复触发纠正重跑

当一轮 LLM 调用以非工具调用结束（`finish_reason != "tool_calls"`）但最终回复为空白（无 content 或仅空白字符）时，agent loop SHALL 注入一条纠正性 `user` 消息提示模型直接给出答案或调用工具，并重跑该轮，而非立即返回空回复。重跑次数 MUST 受上限约束；达到上限后 MUST 停止重跑并返回当前（可能仍为空的）回复，不得无限重试。回复非空白时 MUST NOT 触发纠正（行为与未引入本能力时一致）。阻塞 `run()` 与流式 `run_stream()` 两路均 SHALL 具备该行为。

#### Scenario: 空回复触发一次纠正后得到非空回复
- **WHEN** 首轮最终回复为空白，纠正重跑后模型给出非空回复
- **THEN** loop 不返回空，最终返回纠正后的非空回复

#### Scenario: 持续空回复在上限后停止
- **WHEN** 模型持续返回空白回复直至重试上限
- **THEN** loop 停止重跑、返回当前回复，不无限循环

#### Scenario: 非空回复不触发纠正
- **WHEN** 最终回复非空白
- **THEN** 不注入纠正、不重跑，直接返回该回复

