## ADDED Requirements

### Requirement: 无服务端 askit 任务队列,部署唯一经 apply API
系统 **MUST NOT** 维护任何服务端的 askit 任务队列/工作区表(`askit_tasks` / `askit_task_logs` / `askit_workspaces`)。agent 部署 **MUST** 唯一经幂等 apply API 进行(见「Idempotent agents apply API」);askit 部署器只 POST 编译后的 agent 定义,fleetent 仍是其自身数据库的唯一写者。这些任务队列表是 apply-API 模型之前的遗留,已无任何代码使用,**MUST** 被移除。

#### Scenario: schema 中不存在 askit 任务队列表
- **WHEN** 对空库执行 `alembic upgrade head`
- **THEN** 建出的 schema 中不包含 `askit_tasks` / `askit_task_logs` / `askit_workspaces` 表

#### Scenario: 部署仍只经 apply API
- **WHEN** askit 部署器部署一个 agent
- **THEN** 它经 `POST /admin/agents/apply` 提交编译后的定义,过程不依赖任何服务端任务队列表
