# agent-service-principal Specification

## ADDED Requirements

### Requirement: 为 agent 铸造 service-principal User

系统 SHALL 提供「为某 agent 获取或铸造其 service-principal User」的幂等能力。该 principal SHALL 是 `users` 表中一行，`id` 形如 `agent:<agent_id>`、`role="service"`。重复调用 SHALL 返回同一 principal、不创建重复行。service principal MUST NOT 被签发人类登录会话或 INBOUND `ma-` key，且 MUST NOT 经常规 `set_role` 提权为人类角色。

#### Scenario: 幂等铸造
- **WHEN** 对 agent `42` 两次请求其 service-principal
- **THEN** 两次返回同一 `user_id="agent:42"`，`users` 表中仅一行 `role="service"`

#### Scenario: service principal 不可提权
- **WHEN** 尝试把一个 service principal 的 role 改为 `admin`
- **THEN** 该操作被拒绝，service principal 不获得人类角色权限

### Requirement: run_as 决定凭证 principal

dispatch 解析声明了 connector 的工具凭证时 SHALL 读取对应 `agent_service_grants.run_as`：`user` → 以调用用户 `user_id` 解析；`agent` → 以该 agent 的 service-principal `user_id` 解析；再调用 `connectors.get_credential(principal_id, service, scopes)`。两种 principal 的凭证同存于 `external_credentials`，互不串用。

#### Scenario: run_as=user 取调用用户凭证
- **WHEN** grant 的 `run_as="user"`，用户 u1 触发该工具
- **THEN** 以 `u1` 解析凭证

#### Scenario: run_as=agent 取 agent principal 凭证
- **WHEN** grant 的 `run_as="agent"`，agent `42` 触发该工具
- **THEN** 以 `agent:42` 解析凭证，与任何调用用户的凭证互不串用

#### Scenario: agent principal 未授权则短路
- **WHEN** `run_as="agent"` 但 `(agent:42, service)` 无凭证
- **THEN** 返回 `NeedsConsent`，工具不执行
