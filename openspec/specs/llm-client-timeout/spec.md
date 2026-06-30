# llm-client-timeout Specification

## Purpose
TBD - created by archiving change harden-im-llm-timeout-handling. Update Purpose after archive.
## Requirements
### Requirement: 聊天 LLM client 配置显式超时与有界重试

构造面向聊天补全的 LLM client（`AsyncOpenAI`）时，SHALL 设置显式的 HTTP 超时（区分 connect / read / write / pool）与有界的 SDK 层重试次数（`max_retries`），而非依赖 SDK 默认值。read 超时 MUST 为有限值，使流式调用的 chunk 间停顿有确定的失败边界（避免无界等待或与默认值不一致的行为）。

#### Scenario: client 带显式超时构造
- **WHEN** 构造聊天 LLM client
- **THEN** 该 client 配置了显式的 `timeout`（含有限的 read 超时）

#### Scenario: client 带有界重试
- **WHEN** 构造聊天 LLM client
- **THEN** 该 client 配置了有界的 `max_retries`（>0 且有限）

#### Scenario: 超时阈值可被测试注入
- **WHEN** 测试需要以不同超时阈值构造 client
- **THEN** 超时阈值以模块内可注入常量提供，便于 `monkeypatch` 覆盖（不硬编码为不可替换字面量）

