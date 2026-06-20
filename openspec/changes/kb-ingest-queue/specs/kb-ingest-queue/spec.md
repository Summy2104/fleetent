## ADDED Requirements

### Requirement: 持久 ingest job 队列

系统 SHALL 提供持久的 DB 背 ingest job 队列(`kb_ingest_jobs`,管理库 Alembic)。每条 job SHALL 含 `id`、`tenant_id`、`kb_id`、`connector_ref`(非密 connector 配置引用/内容)、`cred_ref`(Vault 凭据引用,**非明文**)、`status`(pending/claimed/done/failed)、`attempts`、创建/认领/完成时间戳。

#### Scenario: 入队产生 pending job

- **WHEN** 一个 ingest 触发(上传/sync/cron/webhook)发生
- **THEN** 系统插入一条 `status=pending` 的 `kb_ingest_jobs` 记录,携带 `connector_ref` 与 `cred_ref`

#### Scenario: 明文凭据不入队

- **WHEN** 入队时读取 connector 注册表
- **THEN** job 只写入凭据的 **Vault 引用**(`cred_ref`),不写入明文凭据

### Requirement: 原子 claim / done / retry 语义

队列 SHALL 提供原子 claim(单次取一条 pending 置 claimed,并发不重复领取)、done(置 done)、failed+retry(置 failed;`attempts` 未达上限则回 pending 重试,达上限则终态 failed)。

#### Scenario: 并发 claim 不重复

- **WHEN** 两个消费者同时尝试 claim
- **THEN** 同一条 job 只被一个消费者领取(原子 UPDATE),另一个领到下一条或空

#### Scenario: 失败重试到上限

- **WHEN** 一条 job 处理失败且 `attempts` 未达上限
- **THEN** 回到 pending 等重试;达上限则置终态 failed,不再重试

### Requirement: 触发器只入队,不在控制面同步跑 ingest

所有 ingest 触发器(上传/导入、connector sync、cron、webhook)SHALL 改为**入队并返回 job id**,SHALL NOT 在控制面请求线程内同步执行 parse/chunk/embed。`kb_admin_api` 的 sync/导入端点 SHALL 返回 job id(或对 admin sync 提供"入队+等完成"语义)。

#### Scenario: sync 端点不再同步阻塞

- **WHEN** admin 触发 connector sync
- **THEN** 端点入队 job 并立即返回 job id(或入队+等该 job 完成),不在请求线程内跑完整 ingest

#### Scenario: cron / webhook 触发入队

- **WHEN** cron 或 webhook 触发某 KB 的摄取
- **THEN** 系统入队 job,而非同步跑 ingest
