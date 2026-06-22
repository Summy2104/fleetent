## ADDED Requirements

### Requirement: Per-connector opt-in 周期调度
系统 SHALL 支持给每个 KB connector 配置可选的周期 sync 间隔（`sync_interval_seconds`）。该字段 SHALL 默认未设置（NULL），即**默认不自动调度**；仅当显式设为正整数时该 connector 才进入周期调度。被禁用（`enabled=0`）的 connector SHALL NOT 被调度。

#### Scenario: 默认不调度
- **WHEN** 一个 connector 未设置 `sync_interval_seconds`
- **THEN** 调度 sweep 不会为它入队任何 sync job

#### Scenario: opt-in 后按间隔调度
- **WHEN** 一个 enabled connector 设了 `sync_interval_seconds=N`，且距上次调度已 ≥ N 秒
- **THEN** 下一次 sweep 为它入队一个 `connector_sync` job

#### Scenario: 禁用的 connector 不调度
- **WHEN** 一个 connector `enabled=0` 但设了 `sync_interval_seconds`
- **THEN** sweep 不为它入队

### Requirement: 调度经现成队列与 worker
调度 SHALL 复用现有 `kb_ingest_jobs` 队列与 KB ingest worker：sweep 只负责把到期 connector 入队（`enqueue_connector_job`），实际 `run_connector_sync` 由 worker 执行。调度 sweep SHALL 运行在 platform 控制面进程，MUST NOT 在 agent runtime 内执行，MUST NOT 写 agent 侧运行数据。

#### Scenario: sweep 只入队不执行
- **WHEN** sweep 判定某 connector 到期
- **THEN** 它向 `kb_ingest_jobs` 入队一个 `connector_sync` job，由 worker 后续 drain 执行

### Requirement: 轻量去重与重试恢复
sweep 入队后 SHALL 立即推进该 connector 的 `last_scheduled_sync_at`，使下一次 tick 在间隔内不重复入队。失败的 sync SHALL 由下一个到期 tick 自然重试，系统 MUST NOT 依赖幂等锁或多 worker 分布式协调。sweep SHALL 舱壁化：单个 connector 的入队失败只记录日志，不中断整轮 sweep、不使 cron job 抛出。

#### Scenario: 入队后间隔内不重复
- **WHEN** sweep 刚为某 connector 入队并推进了 `last_scheduled_sync_at`
- **THEN** 在 `sync_interval_seconds` 未过去前的后续 tick 不会再为它入队

#### Scenario: 失败下次重试
- **WHEN** 某次 scheduled sync 失败（status=sync_failed / auth_failed）
- **THEN** 下一个到期 tick 照常为该 connector 入队，无需人工干预

#### Scenario: 单 connector 异常不拖垮 sweep
- **WHEN** sweep 处理某 connector 时入队抛错
- **THEN** 记录日志并继续处理其余 connector，cron job 不抛出

### Requirement: 多行 sync 历史
系统 SHALL 在每次 connector sync 完成后追加一行历史记录到 `knowledge_connector_sync_history`（含 connector_id、status、summary、error、started_at、finished_at），与每 connector 一行的 last-status 表并存。系统 SHALL 提供按 connector 查询历史的只读接口。

#### Scenario: 每次 sync 追加历史
- **WHEN** 一次 connector sync 完成（成功或失败）
- **THEN** `knowledge_connector_sync_history` 新增一行记录本次结果，既往行保留

#### Scenario: 可查询历史
- **WHEN** 查询某 connector 的 sync 历史
- **THEN** 返回该 connector 多次 sync 的时间线（最近在前）
