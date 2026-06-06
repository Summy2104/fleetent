# scheduled-task-session-binding Specification

## Purpose
TBD - created by archiving change scheduled-task-session-binding. Update Purpose after archive.
## Requirements

### Requirement: 定时任务 session 绑定语义可配置且显式声明

定时任务每次触发时使用的 session SHALL 由任务的可选 `session_id` 配置显式决定，系统 MUST NOT 对绑定语义做隐式推断。绑定语义恰为两态：声明了 `session_id` 时跨触发复用该固定 session（累积上下文）；未声明时每次触发新建独立 session（不累积）。

#### Scenario: 声明 session_id 时跨触发复用固定 session
- **WHEN** 一个定时任务配置了 `session_id="cron/daily-report"` 并先后触发两次
- **THEN** 两次触发都使用同一 session_id，第二次触发能读取到第一次触发写入的历史上下文

#### Scenario: 未声明 session_id 时每次触发新建独立 session
- **WHEN** 一个定时任务未配置 `session_id`（NULL）并先后触发两次
- **THEN** 两次触发各自使用一个唯一的独立 session_id，第二次触发读取到的历史为空，与第一次互不可见

#### Scenario: 绑定语义不隐式推断
- **WHEN** 任务未声明 `session_id`
- **THEN** 系统不依据 `user_id`、`task_id` 或时间等信息自动派生出一个跨触发复用的固定 session，仅按「每次独立」处理

### Requirement: 默认每次触发独立 session

`session_id` 未配置（NULL）SHALL 为默认语义，即每次触发新建独立、互不可见的 session，使升级后既有任务的可观察行为与「每次从零开始」一致。该默认 MUST 不跨触发累积上下文。

#### Scenario: 默认语义不改变既有无记忆行为
- **WHEN** 一个未配置 `session_id` 的任务连续触发多次
- **THEN** 每次触发都以空历史开始运行，历次之间不共享任何上下文

#### Scenario: 独立 session_id 每次触发唯一
- **WHEN** 同一未配置 `session_id` 的任务触发两次
- **THEN** 两次派生的 session_id 互不相同（携带每次触发唯一的标识），对应两个互不可见的 session 文件

### Requirement: scheduled_tasks 承载可选 session_id 字段

`scheduled_tasks` 表 SHALL 增加可选列 `session_id`（可空，NULL 表示每次独立）。`schedule_store.create` MUST 接受可选 `session_id` 参数并持久化；`list_tasks` 返回的任务字典 MUST 包含 `session_id`。Legacy static YAML task loading is not a current runtime source.

#### Scenario: 创建任务持久化 session_id
- **WHEN** `schedule_store.create(..., session_id="cron/daily")` 被调用
- **THEN** 写入的任务行 `session_id` 为 `"cron/daily"`，`list_tasks` 返回的该任务字典含 `session_id="cron/daily"`

#### Scenario: 未传 session_id 默认 NULL
- **WHEN** `schedule_store.create(...)` 未传 `session_id`
- **THEN** 该任务行 `session_id` 为 NULL，`list_tasks` 返回的字典中 `session_id` 为 None

#### Scenario: Legacy static YAML is not a session source
- **WHEN** a legacy static schedule YAML declares `session_id`
- **THEN** runtime does not load that YAML as current task configuration

### Requirement: 触发时据 session_id 接入 session 持久化

定时任务触发逻辑 SHALL 据任务的 `session_id` 解析出本次使用的 session_id（声明时用固定值，未声明时派生 `cron/{task_id}/{run_uuid}` 形式的唯一值），并在 per-session 锁下读取历史、拼接本次消息运行 agent、将更新后的历史写回。触发 MUST 在 `session_mgr` 的 per-session 锁内 load 与 save，使同一固定 session 的并发触发串行、不互相覆盖。

#### Scenario: 固定 session 触发读历史并写回
- **WHEN** 配置了 `session_id` 的任务触发
- **THEN** 触发前 `session_mgr.load(session_id)` 取到历史，历史与本次 `user` 消息一起传入 `agent_loop.run`，运行后更新的消息列表经 `session_mgr.save(session_id, ...)` 写回同一 session

#### Scenario: 独立 session 派生唯一 id 并写到本次专属文件
- **WHEN** 未配置 `session_id` 的任务触发
- **THEN** 本次派生形如 `cron/{task_id}/{run_uuid}` 的唯一 session_id，`load` 返回空列表，运行结果经 `save` 写到本次专属 session 文件

#### Scenario: 同一固定 session 并发触发串行
- **WHEN** 同一固定 `session_id` 在前一次触发尚未完成持久化时再次触发
- **THEN** 第二次触发经 per-session `asyncio.Lock` 等待第一次完成 load/save 后再读取历史，两次写入不互相覆盖

#### Scenario: 写回顺带刷新 session 元数据
- **WHEN** 触发完成调用 `session_mgr.save`
- **THEN** 传入任务的 `user_id` 与 `agent_name`，使该 session 的元数据索引（最后活跃时间、message_count、归属）一并被刷新
