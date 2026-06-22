## ADDED Requirements

### Requirement: kb-worker 是 ingest 队列的唯一消费者

系统 SHALL 提供长驻进程 `fleetent kb-worker`,作为 `kb_ingest_jobs` 队列的**唯一消费者**:循环 claim(原子)pending job → 调 `knowledge_base.ingest` 核执行摄取 → mark done;失败则 mark failed + retry(至上限)。KB 内容写入 SHALL 只发生在 worker 调核的路径(**单一写入方**)。worker SHALL 经 `db.py` 边界访问队列,SHALL NOT `import fleetent.platform.*`。

#### Scenario: worker drain 队列并写 KB

- **WHEN** 队列有 pending job 且 `fleetent kb-worker` 在跑
- **THEN** worker claim 该 job、调 ingest 核完成摄取、写 KB、置 job done

#### Scenario: 失败重试

- **WHEN** worker 处理某 job 抛错且 attempts 未达上限
- **THEN** job 回 pending 等重试;达上限置终态 failed

#### Scenario: 单一写入方

- **WHEN** 检视所有写 KB 内容的代码路径
- **THEN** 仅 worker 调核这一条;生产无其它写 KB 内容的入口

### Requirement: 生产无绕过队列的 ingest 路径

移除 `kb-ingest-queue` 引入的过渡内联 drain 后,生产 SHALL NOT 存在任何绕过队列/worker 的 ingest 执行路径。直接调 `knowledge_base.ingest` 核 SHALL 仅出现在测试(in-process)。admin sync SHALL 入队 + 轮询 job 状态(同步体验、worker 异步执行;超时后返回 job id + 当前状态,不无限阻塞)。

#### Scenario: 过渡 drain 已移除

- **WHEN** 检视代码
- **THEN** 不存在 `kb-ingest-queue` 阶段的临时内联 drain;消费只经 `fleetent kb-worker`

#### Scenario: admin sync 入队 + 轮询

- **WHEN** admin 触发 sync(execute)
- **THEN** 端点入队 → 轮询 job 至 done/failed 返回结果;若超时则返回 job id + 当前状态
