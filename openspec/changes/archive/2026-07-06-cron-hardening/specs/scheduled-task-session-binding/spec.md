# scheduled-task-session-binding Delta

## ADDED Requirements

### Requirement: session 绑定经 schedule 工具可配置

`schedule` 工具的 `create` SHALL 暴露可选 `session` 参数（字符串，默认空 = 不绑定），非空时透传为任务的 `session_id` 持久化——使「跨触发累积上下文」的既有固定 session 语义（见「定时任务 session 绑定语义可配置且显式声明」）对通过对话创建任务的用户可达（AAA-8209「计数器不递增」场景的正解入口）。参数描述 SHALL 说明两态语义：留空 = 每次触发独立无记忆；指定 = 历次触发共享同一会话上下文。绑定与触发语义本身不变（本要求只补工具入口）。

#### Scenario: 经工具创建固定 session 任务
- **WHEN** an agent calls `schedule(action="create", session="cron/counter", message="计数并报告当前值", ...)`
- **THEN** 任务行持久化 `session_id="cron/counter"`，两次触发共享该会话历史（第二次可读到第一次的计数）

#### Scenario: 省略 session 保持默认独立语义
- **WHEN** `schedule(action="create", ...)` 未提供 `session` 参数
- **THEN** 任务行 `session_id` 为 NULL，每次触发新建独立 session（既有默认行为不变）

#### Scenario: 工具 schema 携带两态语义说明
- **WHEN** the `schedule` tool schema is built and delivered to the model
- **THEN** `session` 参数的描述说明「留空=每次独立；指定=跨触发累积上下文」
