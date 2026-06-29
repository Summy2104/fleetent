## MODIFIED Requirements

### Requirement: kb-worker 是 ingest 队列的唯一消费者

系统 SHALL 提供长驻进程 `fleetent kb-worker`,作为 `kb_ingest_jobs` 队列的**唯一消费者**,处理 ingest 类 job(导入 / sync）以及 `extraction` job:循环 claim(原子)pending job → 按 job_type 调 `knowledge_base.ingest` 核执行摄取,或调 `run_entity_extraction` 执行抽取 → mark done;失败则 mark failed + retry(至上限)。KB 内容与图谱写入 SHALL 只发生在 worker 调核的路径(**单一写入方**)。worker SHALL 经 `db.py` 边界访问队列,SHALL NOT `import fleetent.platform.*`。

#### Scenario: worker drain 队列并写 KB

- **WHEN** 队列有 pending ingest job 且 `fleetent kb-worker` 在跑
- **THEN** worker claim 该 job、调 ingest 核完成摄取、写 KB、置 job done

#### Scenario: worker 消费 extraction job

- **WHEN** 队列有 pending `extraction` job 且 `fleetent kb-worker` 在跑
- **THEN** worker claim 该 job、对目标 document 调 `run_entity_extraction` 写 entities/mentions/relations、置 job done

#### Scenario: 失败重试

- **WHEN** worker 处理某 job 抛错且 attempts 未达上限
- **THEN** job 回 pending 等重试;达上限置终态 failed

#### Scenario: 单一写入方

- **WHEN** 检视所有写 KB 内容与图谱的代码路径
- **THEN** 仅 worker 调核这一条;生产无其它写 KB 内容 / 图谱的入口
