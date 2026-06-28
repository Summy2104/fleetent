# agent-node-placement

## ADDED Requirements

### Requirement: 解除编排时清理 node 上报态
`node_agent_status`(node 上报的 per-agent 运行态投影)MUST NOT 比其对应的编排关系活得更久。当一个 agent 被 unpin(删除其 `agent_placements` 行),或其所在 node 被注销(deregister)时,系统 SHALL 同步删除该 agent / 该 node 的 `node_agent_status` 行,使控制台运行态视图不再为已脱离编排的 agent 显示"幽灵 running 行"。该清理在解除编排的同一写入路径完成(确定性,非后台 GC)。

#### Scenario: unpin 后上报态被清理
- **WHEN** 对一个已 pin 且 `node_agent_status` 中有 `phase=running` 行的 agent 执行 unpin
- **THEN** 其 `agent_placements` 行被删除,且其 `node_agent_status` 行被同步删除
- **AND** 控制台运行态视图不再显示该 agent 的 running 状态

#### Scenario: 注销 node 清理其上报态
- **WHEN** 一个 node 被注销(deregister)
- **THEN** 该 node 在 `node_agent_status` 中的上报行被删除,不留陈旧记录

#### Scenario: 删除 agent 经 CASCADE 清理
- **WHEN** 一个 agent 被硬删除
- **THEN** 其 `node_agent_status` 行随 `agent_id` 外键 CASCADE 删除(既有行为保持)
