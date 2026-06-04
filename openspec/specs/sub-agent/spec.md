# sub-agent Specification

## Purpose
并行子 agent 执行能力。父 agent 通过 `sub_agent` 工具派发多个任务，经 `asyncio.gather` 并发执行，单个任务失败不影响其余结果一并回收。每个子 agent 以纯净上下文启动（仅含父给定 prompt，不继承父对话历史），并在父的 `user_id` 与 agent 策略下运行；子 agent 不得再派生子 agent（最大深度 1）。子 agent 的 eval trace 记录 `parent_session_id` 以建立父子链路。

## Requirements

### Requirement: Parallel sub-agent execution
The system SHALL allow a parent agent to dispatch multiple sub-agents that run concurrently via `asyncio.gather`.

#### Scenario: Two tasks in parallel
- **WHEN** parent agent calls the `sub_agent` tool with `tasks=[{name: "A", prompt: "..."}, {name: "B", prompt: "..."}]`
- **THEN** both tasks run concurrently and results are returned when both complete

#### Scenario: Partial failure
- **WHEN** one sub-agent task raises an exception
- **THEN** the parent receives the successful results alongside the error for the failed task, and decides whether to continue

### Requirement: Fresh context per sub-agent
Each sub-agent SHALL start with only the prompt provided by the parent, not the parent's conversation history.

#### Scenario: Sub-agent context isolation
- **WHEN** a sub-agent is created with `prompt="analyze this document"`
- **THEN** its `messages` list starts as `[{"role": "user", "content": "analyze this document"}]` with no parent history

### Requirement: Depth limit
The system SHALL prevent sub-agents from spawning further sub-agents (max depth = 1 child level).

#### Scenario: Child cannot spawn grandchildren
- **WHEN** a sub-agent tries to call the `sub_agent` tool
- **THEN** the tool returns an error: "sub-agent cannot spawn further sub-agents"

### Requirement: Permission inheritance
Sub-agents SHALL execute under the same `user_id` as the parent, inheriting the same agent policy.

#### Scenario: Sub-agent respects parent user permissions
- **WHEN** a sub-agent calls a tool
- **THEN** `tool_registry.dispatch` checks `allowed_tools` for the same `agent_id` as the parent session

### Requirement: Trace linkage
Sub-agent eval traces SHALL record the parent session ID.

#### Scenario: Sub-agent trace contains parent reference
- **WHEN** a sub-agent run completes and logs to `eval_logger`
- **THEN** the trace includes `parent_session_id` referencing the parent session
