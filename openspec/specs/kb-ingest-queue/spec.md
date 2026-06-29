# kb-ingest-queue Specification

## Purpose
TBD - created by archiving change kb-ingest-queue. Update Purpose after archive.
## Requirements
### Requirement: 持久 ingest job 队列

系统 SHALL 提供持久的 DB 背 ingest job 队列,归 **standalone KB 服务本地**(KB 主机本地 SQLite,**非** management.db / 非平台)。每条 job SHALL 含 `id`、`tenant_id`、`kb_id`、`connector_ref`(非密 connector 配置引用/内容)、`cred_ref`(本地凭据引用 `env:`/`file://`,**非明文**)、`status`(pending/claimed/done/failed)、`attempts`、创建/认领/完成时间戳。平台托管的 management.db 队列(`kb_ingest_jobs` in management.db)**已退役**。

#### Scenario: standalone 入队产生 pending job

- **WHEN** standalone KB 服务的 ingest 触发(自有 sweep 的 connector sync / 自动 extraction)发生
- **THEN** 系统在 KB 本地队列插入一条 `status=pending` 记录,携带 `connector_ref` 与本地 `cred_ref`
- **AND** 不读写 management.db

#### Scenario: 明文凭据不入队

- **WHEN** 入队时读取 connector 配置
- **THEN** job 只写入凭据的**本地引用**(`cred_ref`,`env:`/`file://`),不写入明文凭据

### Requirement: 原子 claim / done / retry 语义

队列 SHALL 提供原子 claim(单次取一条 pending 置 claimed,并发不重复领取)、done(置 done)、failed+retry(置 failed;`attempts` 未达上限则回 pending 重试,达上限则终态 failed)。

#### Scenario: 并发 claim 不重复

- **WHEN** 两个消费者同时尝试 claim
- **THEN** 同一条 job 只被一个消费者领取(原子 UPDATE),另一个领到下一条或空

#### Scenario: 失败重试到上限

- **WHEN** 一条 job 处理失败且 `attempts` 未达上限
- **THEN** 回到 pending 等重试;达上限则置终态 failed,不再重试

### Requirement: 触发器只入队,不在控制面同步跑 ingest

所有当前已存在的 ingest 触发器(上传/导入、connector sync)SHALL 改为**先入队再消费**,SHALL NOT 直接在旧的控制面 execute 路径里同步 `asyncio.run` 跑完整 ingest。`kb_admin_api` 的 sync/导入端点 SHALL 返回 job id(或对 admin sync 提供"入队+等完成"语义)。

#### Scenario: sync 端点不再同步阻塞

- **WHEN** admin 触发 connector sync
- **THEN** 端点入队 job 并立即返回 job id(或入队+等该 job 完成),不在请求线程内跑完整 ingest

#### Scenario: 未来新增 trigger 复用同一入队 seam

- **WHEN** 后续新增 cron 或 webhook 形式的 KB ingest 触发器
- **THEN** 它们 SHALL 复用同一 `kb_ingest_jobs` enqueue seam,而非另起同步执行路径
