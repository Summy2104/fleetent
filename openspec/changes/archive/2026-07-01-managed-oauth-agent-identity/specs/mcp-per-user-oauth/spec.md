## MODIFIED Requirements

### Requirement: token 按 user×agent×server 隔离

per-user token 的存储与查取 SHALL 以 `(user_id, agent_id, server_id)` 三元组为键。一个 agent 下某用户的授权 MUST NOT 被另一个 agent 使用;同一用户对不同 agent MUST 分别授权。token 解析 MUST 使用当前调用消息的发送者身份(principal.user_id),MUST NOT 以会话/频道/对话为授权归属。

三元组中的 `agent_id` SHALL 为发起该调用的运行 agent 的身份。MCP client SHALL 在其公开工具调用入口归一化该身份:当调用方未提供 agent 身份时(managed IM 轮次不向 `loop.run()` 透传 `agent_name`,导致工具上下文身份为空),SHALL 回退到本进程唯一活跃 agent(`agent_config.active_agent()`)的名字;进程内不存在唯一活跃 agent(多 agent index)时保持调用方原值。归一化 SHALL 只发生一次并一致流转至 token 解析、授权触发(pending 登记)与子进程凭据注入,MUST NOT 以空身份落库致三元组隔离失效,且 MUST NOT 改变 workspace/exchange 的 scope 归属。

#### Scenario: agent1 的授权不可用于 agent2
- **WHEN** 用户在 agent1 下完成对某 server 的授权,随后在 agent2 下调用同一 server
- **THEN** agent2 查 `(user, agent2, server)` 无 token → 触发 agent2 自己的授权流程,绝不复用 agent1 的 token

#### Scenario: 共享频道中按发送者隔离
- **WHEN** 用户 B 在用户 A 开启的会话/消息列中发消息并触发该 server 的工具调用
- **THEN** token 按 B 的 `user_id` 解析(B 无 token 则 B 被要求自己授权),绝不复用 A 的 token

#### Scenario: 调用方未透传身份时回退活跃 agent
- **WHEN** managed IM 轮次触发 per-user OAuth,工具上下文未携带 agent 名字(空),而本进程正运行唯一 agent
- **THEN** MCP client 以该活跃 agent 的名字补全三元组的 `agent_id`(而非空串),使 pending / token 按真实 agent 身份隔离

#### Scenario: 多 agent 进程保持调用方原值
- **WHEN** 进程内发布了多个 agent(无唯一活跃 agent)且调用方已透传 agent 身份
- **THEN** MCP client 采用调用方透传的身份,不以活跃 agent 覆盖
