## ADDED Requirements

### Requirement: kb-worker 消费 reindex job

kb-worker SHALL 消费 `reindex` 类型的 job,作为 KB 向量索引重建的**唯一写者**。消费时 SHALL 由 job 的 `tenant_id`/`kb_id` 构造重建请求,经 **`vector_store` 公共 reindex API**(非内部实现)从该 KB 在 `kb.db` 的存量 chunk 重建其向量命名空间;重建所用命名空间 SHALL 与 ingest 写入该 KB 向量时的命名空间**一致**(否则重建到错误命名空间、检索读不到)。reindex job 的入队方为 `fleetent kb reindex`(见 kb-standalone-ingest);单 reindex 失败 SHALL 记录到 job 终态,不影响其它 job。

#### Scenario: worker 执行 reindex job
- **WHEN** 队列有 pending `reindex` job 且 `fleetent kb worker` 在跑
- **THEN** worker 认领并经 `vector_store` 公共 reindex API 重建该 KB 的向量命名空间(从存量 chunk re-embed)
- **AND** 重建后该 KB 检索命中与重建前一致(命名空间对齐)

#### Scenario: reindex 失败落终态
- **WHEN** 某 `reindex` job 执行中失败
- **THEN** 该 job 记为 failed(带错误摘要),不阻塞后续 job,不破坏既有向量库可读性
