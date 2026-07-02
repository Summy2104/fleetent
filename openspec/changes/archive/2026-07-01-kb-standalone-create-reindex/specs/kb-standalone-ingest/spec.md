## ADDED Requirements

### Requirement: 手动建库命令

KB 服务 SHALL 提供命令式建库入口 `fleetent kb create`,在指定租户创建一个知识库,**纯 KB 服务侧、不依赖 platform**。命令 SHALL 复用 `--config <kb-service.yaml>` 解析 tenant_id 与 data_dir(与 `kb serve`/`kb worker`/`kb ingest` 同源),并调知识库管理公共 API 在本租户 `kb.db` 建库。建库 SHALL 幂等:目标 KB 已存在时以成功 no-op 返回(打印现状),不报错、不重复创建。

- 命令签名 SHALL 为 `fleetent kb create --config <kb-service.yaml> --kb <kb_id> [--description <text>]`。
- 全程 SHALL NOT 读写 management.db、SHALL NOT 依赖 platform 或 admin API。

#### Scenario: standalone 建库
- **WHEN** 运维运行 `fleetent kb create --config <kb-service.yaml> --kb <kb_id>`
- **THEN** 本租户 `kb.db` 出现该 KB,后续 `kb ingest`/`kb extract`/检索可用
- **AND** 全程不依赖 platform 或 management.db

#### Scenario: 重复建库幂等
- **WHEN** 对已存在的 KB 再次运行 `kb create`
- **THEN** 命令以成功返回(no-op),不报错、不产生重复记录

### Requirement: 手动重建索引命令

KB 服务 SHALL 提供命令式向量重建入口 `fleetent kb reindex`,对指定 KB 从 `kb.db` 存量 chunk 重建其向量索引(`kb_vectors.db`),**纯 KB 服务侧、不依赖 platform**。重建 SHALL 经**入队**完成:命令把一个 `reindex` job 入本租户 `kb_ingest_queue.db`,由运行中的 kb-worker 作为**唯一写者**执行重建(经 `vector_store` 公共 reindex API);命令 SHALL NOT 在自身进程内直写 `kb_vectors.db`(守单写者纪律,与 `kb ingest`/`kb extract` 同形)。入队前 SHALL 校验目标 KB 存在。`--wait` 时 SHALL 阻塞至 job 终态并打印重建计数,超时提示检查 kb-worker。

#### Scenario: 入队重建并由 worker 执行
- **WHEN** 运维运行 `fleetent kb reindex --config <kb-service.yaml> --kb <kb_id>`
- **THEN** 一个 `reindex` job 入本租户 `kb_ingest_queue.db`
- **AND** 运行中的 kb-worker 消费它,按该 KB 的向量命名空间从存量 chunk 重建 `kb_vectors.db`,全程不依赖 platform

#### Scenario: 目标 KB 不存在
- **WHEN** `--kb` 指向本租户 `kb.db` 不存在的 KB
- **THEN** 命令报清晰错误、不入队

#### Scenario: --wait 回报结果
- **WHEN** 运维加 `--wait`
- **THEN** 命令阻塞至该 reindex job 终态并打印重建计数(如 namespace/重建条数)
- **AND** 若超时未被消费,提示检查 kb-worker 是否在运行
