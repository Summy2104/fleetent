# agent-oauth-binding Specification

## ADDED Requirements

### Requirement: run_as=agent 解析生效

`agent_service_grants.run_as="agent"` 的绑定在 dispatch 时 SHALL 解析为该 agent 的 service-principal 凭证（见 `agent-service-principal`），而非调用用户的凭证。`run_as="user"`（默认）行为不变。run_as 的取值 SHALL 仅由 grant 承载，MUST NOT 暴露为 LLM 可见的工具参数。

#### Scenario: run_as=agent 走 agent principal
- **WHEN** agent `ops` 对服务 `internal-kb` 的 grant `run_as="agent"`，`ops` 调用对应工具
- **THEN** 凭证以 `ops` 的 service-principal 解析，调用用户身份不参与该次凭证解析

#### Scenario: run_as 不进 LLM schema
- **WHEN** 对声明 connector 的工具调用 `get_schemas()`
- **THEN** 返回 schema 不含 `run_as` 信息
