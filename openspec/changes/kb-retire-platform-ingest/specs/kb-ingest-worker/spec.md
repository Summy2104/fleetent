## MODIFIED Requirements

### Requirement: kb-worker 是 ingest 队列的唯一消费者

系统 SHALL 提供长驻 worker(随 **standalone KB 服务**运行),作为 **KB 服务本地** ingest 队列的**唯一消费者**,处理 connector sync 与 `extraction` job:循环 claim(原子)pending job → 按 job_type 调 `knowledge_base.ingest` 核执行摄取,或调 `run_entity_extraction` 执行抽取 → mark done;失败则 mark failed + retry(至上限)。KB 内容与图谱写入 SHALL 只发生在 worker 调核的路径(**单一写入方**)。worker SHALL 经 `db.py` 边界访问**本地**队列,SHALL NOT `import fleetent.platform.*`。平台启动、drain management.db 队列的 kb-worker 接线**已退役**。

#### Scenario: worker drain 本地队列并写 KB

- **WHEN** KB 本地队列有 pending job 且 worker 在跑
- **THEN** worker claim 该 job、调核完成摄取/抽取、写 KB、置 job done
- **AND** 不读写 management.db

#### Scenario: worker 消费 extraction job

- **WHEN** 本地队列有 pending `extraction` job 且 worker 在跑
- **THEN** worker claim 该 job、对目标 document 调 `run_entity_extraction` 写 entities/mentions/relations、置 job done

#### Scenario: 失败重试

- **WHEN** worker 处理某 job 抛错且 attempts 未达上限
- **THEN** job 回 pending 等重试;达上限置终态 failed
