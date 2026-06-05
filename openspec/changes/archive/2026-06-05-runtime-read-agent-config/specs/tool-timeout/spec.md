## MODIFIED Requirements

### Requirement: 超时时限可配置且 per-tool 覆盖全局默认

工具超时时限 SHALL 可配置：存在一个全局默认时限（默认 30 秒），其取值 SHALL 来自当前 agent 的配置（`agent.yaml` 的 `tool_default_timeout_seconds`）而非全局 `Settings`，未配置时回退至 30 秒默认。单个工具 MAY 经 `@tool(timeout=...)` 声明覆盖全局默认的 per-tool 时限。某工具的有效超时为：声明了 per-tool 时限则用之，否则用该 agent 解析出的全局默认。全局默认与 per-tool 时限元数据 MUST 可注入（模块级常量可 monkeypatch），不依赖全局可变状态，且 per-tool 超时元数据 MUST NOT 出现在 LLM 可见的工具 schema 中。

#### Scenario: 未声明 per-tool 时限用 agent 配置的全局默认

- **WHEN** 一个工具未经 `@tool(timeout=...)` 声明 per-tool 时限，且当前 agent 的 `agent.yaml` 声明 `tool_default_timeout_seconds: 15`
- **THEN** 其有效超时为 15 秒

#### Scenario: agent 未配置时回退 30 秒默认

- **WHEN** 当前 agent 未声明 `tool_default_timeout_seconds`，且某工具未声明 per-tool 时限
- **THEN** 其有效超时为 30 秒默认

#### Scenario: per-tool 时限覆盖全局默认

- **WHEN** 一个工具经 `@tool(timeout=5)` 声明 per-tool 时限
- **THEN** 其有效超时为 5 秒，覆盖全局默认

#### Scenario: 超时元数据不进 LLM schema

- **WHEN** 导出工具的 LLM schema
- **THEN** schema 中不包含该工具的超时时限元数据（与 `risk_level`/`connector` 一致，仅作调度时元数据）
