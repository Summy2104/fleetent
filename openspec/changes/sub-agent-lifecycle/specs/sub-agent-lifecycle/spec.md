## ADDED Requirements

### Requirement: 子 agent 生命周期状态机

每个子 agent 任务 SHALL 被赋予明确的生命周期状态，取值限于 `pending` / `running` / `succeeded` / `failed` / `timed_out` / `cancelled`。状态迁移 MUST 单向不可逆：仅允许 `pending → running`、`running → succeeded`、`running → failed`、`running → timed_out`、`running → cancelled`、`pending → cancelled`；任何其他迁移 MUST 被拒绝并报错，MUST NOT 静默接受。终态（`succeeded` / `failed` / `timed_out` / `cancelled`）MUST NOT 再迁移到任何状态。

#### Scenario: 子任务登记为 pending
- **WHEN** 一个子 agent 任务被登记但尚未启动
- **THEN** 其生命周期状态为 `pending`，`started_at` 与 `ended_at` 均为空

#### Scenario: 启动后迁移到 running
- **WHEN** 子任务开始执行 `agent_loop`
- **THEN** 状态由 `pending` 迁移到 `running`，记录 `started_at`

#### Scenario: 正常完成迁移到 succeeded
- **WHEN** 子任务的 `agent_loop` 正常返回结果
- **THEN** 状态由 `running` 迁移到 `succeeded`，记录 `ended_at`，`error` 为空

#### Scenario: 异常迁移到 failed
- **WHEN** 子任务的 `agent_loop` 抛出非取消、非超时的异常
- **THEN** 状态由 `running` 迁移到 `failed`，记录 `ended_at` 与 `error` 摘要

#### Scenario: 非法迁移被拒绝
- **WHEN** 试图对一个已处于终态（如 `succeeded`）的子任务再次迁移状态
- **THEN** 系统报错（抛出明确异常）并记录，不接受该非法迁移

### Requirement: 子任务超时控制

子 agent 的每个子任务 SHALL 被赋予一个超时配额；执行 MUST 通过为该子任务构造带 `deadline` 的 cancel token（复用 `cancellation.CancelToken`，「超时 = 带 deadline 的 token」）实现超时。该子任务 token MUST 经 `parent` 链接挂接到本批的外部 / 父级 token，使**外部 / 父取消能传播到子任务 token**；子任务在既有检查点轮询其 token 即可同时反映「自身 deadline」与「父 / 外部取消」两个源，MUST NOT 引入额外的轮询看门狗或额外延迟。超时配额未显式指定时 SHALL 回退到默认值 `300` 秒，且该默认值 MUST 可经配置（`Settings`）覆盖；优先级为：调用参数 > 配置 > 默认。子任务到达 deadline 时 SHALL 以 `timed_out` 终态收束，且 MUST NOT 拖累同批其余子任务的执行与收束。

#### Scenario: 超时进入 timed_out
- **WHEN** 某子任务执行时长超过其超时配额（cancel token 的 deadline 已过）
- **THEN** 该子任务状态迁移到 `timed_out`，记录 `ended_at`

#### Scenario: 单子任务超时不拖累同批
- **WHEN** 同一批并行子任务中一个超时、其余在配额内正常完成
- **THEN** 超时者收束为 `timed_out`，其余各自收束为 `succeeded`，互不影响

#### Scenario: 默认超时回退
- **WHEN** 创建子任务时未显式指定超时配额，且配置未覆盖
- **THEN** 该子任务的超时配额为默认 `300` 秒

#### Scenario: 配置覆盖默认超时
- **WHEN** 配置声明子 agent 超时为非默认值（如 `Settings.sub_agent_timeout_seconds=120`），且调用未显式传超时
- **THEN** 该子任务的超时配额为配置值 `120` 秒

### Requirement: 区分超时与外部取消终态

子任务因 cancel token 停止时，系统 SHALL 区分两种终态：因 deadline 到期而停止的记为 `timed_out`；因外部 / 父级显式取消（`cancel()`，经子任务 token 的 `parent` 链接传播）而停止的记为 `cancelled`。判定 MUST 依据子任务 token 自身的 deadline 是否已过：deadline 已过记 `timed_out`，否则记 `cancelled`。

#### Scenario: 外部取消进入 cancelled
- **WHEN** 一个外部 cancel token 在子任务 deadline 之前被显式取消
- **THEN** 受影响子任务状态迁移到 `cancelled`（而非 `timed_out`），记录 `ended_at`

#### Scenario: 父 batch token 取消经 parent 链接传播到在途子任务
- **WHEN** 一批在途子任务的父 / 外部 cancel token 在各子任务 deadline 之前被取消
- **THEN** 各在途子任务经其 token 的 `parent` 链接被取消并收束为 `cancelled`（而非 `timed_out`），记录 `ended_at`

#### Scenario: 启动前被取消
- **WHEN** 外部取消在子任务尚处于 `pending`（未启动）时到达
- **THEN** 状态由 `pending` 迁移到 `cancelled`，`started_at` 为空

### Requirement: 生命周期状态可观测

子 agent 生命周期记录 SHALL 可按 `parent_session_id` 查询，返回该批所有子任务及其当前状态、各时间戳与错误信息。**运维 / 外部观察者**（另一进程查 `users.db`）SHALL 能实时查询在途子任务状态；**主 agent** 在批 `gather` 结束后 SHALL 能查询历史记录（主 agent 在被挂起期间不实时感知自己子任务的中途状态），不再 fire-and-forget。查询 MUST 反映状态迁移后的最新值。

#### Scenario: 按 parent_session_id 列出子任务
- **WHEN** 以某 `parent_session_id` 查询生命周期记录
- **THEN** 返回该批每个子任务的 `name`、当前 `state`、`created_at` / `started_at` / `ended_at` 与 `error`

#### Scenario: 查询反映最新状态
- **WHEN** 某子任务由 `running` 迁移到终态后再次查询
- **THEN** 查询结果中该子任务的 `state` 为其终态，`ended_at` 已填充

### Requirement: 生命周期状态持久化

子 agent 生命周期记录 SHALL 持久化到 `users.db` 的 `sub_agent_runs` 表（标准库 `sqlite3`，不使用 ORM），进程重启后历史记录 MUST 仍可查询。建表 MUST 幂等（`CREATE TABLE IF NOT EXISTS`），数据库路径 MUST 可经测试注入（monkeypatch `DB_PATH`）。

#### Scenario: 记录持久化后可重新读取
- **WHEN** 一个子任务的生命周期记录写入后，重新打开数据库连接查询
- **THEN** 该记录连同其状态与时间戳被原样读回

#### Scenario: 建表幂等
- **WHEN** 在已存在 `sub_agent_runs` 表的库上再次初始化
- **THEN** 初始化不报错，既有数据不丢失

### Requirement: 既有并行执行行为向后兼容

接入生命周期管理后，子 agent 执行器的批量返回值（`list[SubAgentResult]`）语义与字段 SHALL 保持不变；未显式传入超时与外部取消令牌时，执行行为 MUST 与现状等价。生命周期记录与超时为旁路增强，MUST NOT 改变既有并行执行、独立上下文、深度限制、权限继承与 trace 关联的行为。

#### Scenario: 不传超时与取消令牌时行为不变
- **WHEN** 调用子 agent 执行器但不传超时配额与外部 cancel token
- **THEN** 返回的 `list[SubAgentResult]` 与现状等价（成功者带 result、失败者带 error），子任务以默认超时受保护

#### Scenario: 生命周期为旁路不破坏批返回
- **WHEN** 一批子任务中部分成功、部分失败并各自写入生命周期记录
- **THEN** 批返回值仍含每个子任务对应的 `SubAgentResult`，与生命周期记录一致而不互相覆盖
